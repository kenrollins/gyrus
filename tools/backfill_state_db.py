#!/usr/bin/env python3
"""Backfill gyrus from Hermes's own capture (`state.db` on shadesmar).

Replaces the cancelled openbrain import (docs/references/OPENBRAIN-AUDIT.md):
Hermes's per-turn store is the real corpus — 158 sessions / 10.5k messages of
Ken's actual work, versus a retired system's 500 rows of mostly news.

Design constraints, each learned the hard way:
  - CRON IS EXCLUDED. The golden-set probe showed a scheduled job's own prompt
    extracted as "Ken prefers..." — five months of automated radar output would
    become fake memory. Filter at the source, not after.
  - WINDOWS, NOT WHOLE SESSIONS. Long conference sessions blow past serving
    contexts; windows also give extraction the cross-turn context that catches
    recurrence-flavoured preferences.
  - IDEMPOTENT + RESUMABLE. Turns are stored with extract=false and marked
    extracted only when their window succeeds, so a re-run finishes the job
    instead of duplicating it (facts dedupe by hash/cosine anyway).

Usage:
  python3 tools/backfill_state_db.py --dry-run            # counts only
  python3 tools/backfill_state_db.py --limit-sessions 3   # a taste
  python3 tools/backfill_state_db.py                      # the lot
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GYRUS = "http://10.0.13.11:8000"
SSH_HOST = "agent@shadesmar"
STATE_DB = "/home/agent/.hermes/state.db"

# Runs ON shadesmar; emits one JSON object per session on stdout.
DUMPER = r'''
import json, sqlite3, sys
c = sqlite3.connect("%(db)s")
c.row_factory = sqlite3.Row
sessions = c.execute("""
    SELECT id, COALESCE(title,'') AS title, COALESCE(source,'') AS source
    FROM sessions WHERE COALESCE(source,'') != 'cron' ORDER BY started_at
""").fetchall()
for s in sessions:
    msgs = c.execute("""
        SELECT role, COALESCE(content,'') AS content, timestamp
        FROM messages WHERE session_id = ? AND role IN ('user','assistant')
          AND COALESCE(content,'') != ''
        ORDER BY CAST(timestamp AS INTEGER), id
    """, (s["id"],)).fetchall()
    if not msgs:
        continue
    print(json.dumps({
        "session_id": s["id"], "title": s["title"], "source": s["source"],
        "messages": [{"role": m["role"], "content": m["content"][:4000],
                      "ts": m["timestamp"]} for m in msgs],
    }))
''' % {"db": STATE_DB}


def post(path: str, body: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        GYRUS + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def pair_turns(messages: list[dict]) -> list[dict]:
    """Reconstruct turns (a user message plus the assistant reply that follows).

    Hermes stores messages, gyrus's episodic tier stores turns. Consecutive
    user messages (Ken firing notes rapidly during a conference — very common
    in this corpus) each become their own turn rather than being merged.
    """
    turns, pending = [], None
    for m in messages:
        if m["role"] == "user":
            if pending is not None:
                turns.append({"user_text": pending, "assistant_text": ""})
            pending = m["content"]
        else:
            turns.append({"user_text": pending or "", "assistant_text": m["content"]})
            pending = None
    if pending is not None:
        turns.append({"user_text": pending, "assistant_text": ""})
    return turns


def windows(messages: list[dict], size: int, overlap: int):
    step = max(1, size - overlap)
    for i in range(0, len(messages), step):
        chunk = messages[i:i + size]
        if chunk:
            yield chunk
        if i + size >= len(messages):
            break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit-sessions", type=int, default=0)
    ap.add_argument("--window", type=int, default=12, help="messages per extraction window")
    ap.add_argument("--overlap", type=int, default=2)
    ap.add_argument("--parallel", type=int, default=3,
                    help="concurrent extraction windows (kaiju serves both models)")
    args = ap.parse_args()

    print(f"dumping sessions from {SSH_HOST}:{STATE_DB} (cron excluded)…", file=sys.stderr)
    r = subprocess.run(["ssh", SSH_HOST, "python3", "-"], input=DUMPER,
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        return 1
    sessions = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    if args.limit_sessions:
        sessions = sessions[-args.limit_sessions:]     # newest are most relevant
    total_msgs = sum(len(s["messages"]) for s in sessions)
    n_windows = sum(len(list(windows(s["messages"], args.window, args.overlap))) for s in sessions)
    print(f"{len(sessions)} sessions, {total_msgs} messages, ~{n_windows} extraction windows")
    if args.dry_run:
        return 0

    def get(path: str) -> dict:
        with urllib.request.urlopen(GYRUS + path, timeout=30) as r:
            return json.load(r)

    t0, facts_total, new_total = time.time(), 0, 0
    for si, s in enumerate(sessions, 1):
        turn_ids = []
        # Resumable: a re-run (after a crash, or after the service restarted
        # mid-backfill) must FILL GAPS, not duplicate the episodic record.
        # Facts dedupe by hash/cosine, but turns have no natural key, so the
        # guard lives here.
        try:
            already = get(f"/v1/sessions/{urllib.parse.quote(s['session_id'], safe='')}")
        except Exception:                                        # noqa: BLE001
            already = {"turns": 0}
        for t in ([] if already.get("turns") else pair_turns(s["messages"])):
            try:
                turn_ids.append(post("/v1/turns", {
                    "session_id": s["session_id"], "platform": s["source"] or "backfill",
                    "user_text": t["user_text"], "assistant_text": t["assistant_text"],
                    "meta": {"backfill": True, "title": s["title"]},
                    "extract": False}, timeout=30)["id"])
            except Exception as e:                                   # noqa: BLE001
                print(f"  turn post failed ({s['session_id'][:16]}): {e}", file=sys.stderr)
        def run_window(chunk):
            try:
                return post("/v1/extract-window", {
                    "session_id": s["session_id"],
                    "messages": [{"role": m["role"], "content": m["content"]} for m in chunk],
                    "turn_ids": []})     # marked at session level below
            except Exception as e:                                   # noqa: BLE001
                print(f"  window failed ({s['session_id'][:16]}): {e}", file=sys.stderr)
                return {"extracted": 0, "new": 0}

        chunks = list(windows(s["messages"], args.window, args.overlap))
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            for out in ex.map(run_window, chunks):
                facts_total += out["extracted"]
                new_total += out["new"]
        if turn_ids:
            try:
                post("/v1/turns/mark-extracted", {"turn_ids": turn_ids}, timeout=60)
            except Exception:                                        # noqa: BLE001
                pass
        el = time.time() - t0
        print(f"[{si}/{len(sessions)}] {s['title'][:44]:44s} "
              f"{len(turn_ids):4d} turns | {facts_total:5d} facts, {new_total:5d} new "
              f"| {el/60:.1f}m")
    print(f"\ndone: {facts_total} extracted, {new_total} new memories, "
          f"{(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
