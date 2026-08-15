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


def turn_messages(t: dict) -> list[dict]:
    """The faithful message list for one turn, for episodic_turns.messages.

    pair_turns() emits half-empty turns by design (consecutive user notes, a
    split assistant reply), so a blank side is dropped rather than stored as
    an empty message.
    """
    out = []
    if (t["user_text"] or "").strip():
        out.append({"role": "user", "content": t["user_text"]})
    if (t["assistant_text"] or "").strip():
        out.append({"role": "assistant", "content": t["assistant_text"]})
    return out


def windows(turns: list[dict], size: int, overlap: int):
    """Group TURNS (not raw messages) into extraction windows.

    Windowing over turns rather than the source message list is what lets each
    window carry the real `turn_ids` it covers, so /v1/extract-window stamps
    them in the same transaction that writes the facts. The previous version
    windowed over messages, passed `turn_ids: []`, and deferred marking to a
    session-level call that a resumed run never made — 465 turns stranded.

    Overlap is carried for CONTEXT only; each window claims just its own new
    turns. Two rules keep that true, and both were got wrong once:

      - advance by len(chunk), NOT by `size - overlap`. Stepping by the
        stride while claiming the whole chunk makes consecutive windows claim
        the same turns, extracting a third of the corpus twice at full 70B
        cost for facts that only dedupe away.
      - `claim` holds turn DICTS, not ids. The dry-run counts windows before
        any turn has been posted, so requiring `t["id"]` here made every
        invocation of this tool raise KeyError before it did anything.
    """
    i = 0
    while i < len(turns):
        chunk = turns[i:i + size]
        if not chunk:
            break
        context = turns[max(0, i - overlap):i]
        yield {"turns": context + chunk, "claim": chunk}
        i += len(chunk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit-sessions", type=int, default=0)
    ap.add_argument("--window", type=int, default=6, help="turns per extraction window")
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
    n_windows = sum(len(list(windows(pair_turns(s["messages"]), args.window, args.overlap)))
                    for s in sessions)
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
            already = {"turns": 0, "pending": 1}
        # Skip sessions already fully extracted — re-running every window each
        # pass is what made this take hours and barely touch the gap.
        if already.get("turns") and not already.get("pending"):
            print(f"[{si}/{len(sessions)}] {s['title'][:40]:40s} skip (complete)")
            continue
        # A session that is PARTLY here is a repair job, not an import job:
        # its turns already exist, so re-posting them would duplicate the
        # episodic record and re-windowing from source would extract turns
        # this tool can no longer identify by id. tools/backfill_pending.py
        # owns that case — it reads the pending turns from the DB and windows
        # them with their real ids. (Silently doing nothing here, while still
        # burning a full re-extraction, is precisely what stranded 465 turns.)
        if already.get("turns"):
            print(f"[{si}/{len(sessions)}] {s['title'][:40]:40s} "
                  f"partial ({already['pending']} pending) — run tools/backfill_pending.py",
                  file=sys.stderr)
            continue

        turns = pair_turns(s["messages"])
        for idx, t in enumerate(turns):
            try:
                t["id"] = post("/v1/turns", {
                    "session_id": s["session_id"], "platform": s["source"] or "backfill",
                    "turn_index": idx,
                    "user_text": t["user_text"], "assistant_text": t["assistant_text"],
                    # Store the verbatim message list too: `messages` is what the
                    # M3 causal-attribution judge reads (outcomes.py), and leaving
                    # it NULL made every backfilled turn invisible to it.
                    "messages": turn_messages(t),
                    "meta": {"backfill": True, "title": s["title"]},
                    "extract": False}, timeout=30)["id"]
                turn_ids.append(t["id"])
            except Exception as e:                                   # noqa: BLE001
                print(f"  turn post failed ({s['session_id'][:16]}): {e}", file=sys.stderr)

        def run_window(w):
            try:
                # Real turn_ids: the route stamps them in the same transaction
                # it persists the facts, so there is no separate bookkeeping
                # step to lose, and a re-run resumes exactly where this stopped.
                return post("/v1/extract-window", {
                    "session_id": s["session_id"],
                    "messages": [m for t in w["turns"] for m in turn_messages(t)],
                    "turn_ids": [t["id"] for t in w["claim"] if t.get("id")]})
            except Exception as e:                                   # noqa: BLE001
                # 503 = inference unavailable; nothing was stamped, so these
                # turns stay pending for the next run rather than vanishing.
                print(f"  window failed ({s['session_id'][:16]}): {e}", file=sys.stderr)
                return {"extracted": 0, "new": 0}

        chunks = [w for w in windows([t for t in turns if t.get("id")],
                                     args.window, args.overlap)]
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            for out in ex.map(run_window, chunks):
                facts_total += out["extracted"]
                new_total += out["new"]
        el = time.time() - t0
        print(f"[{si}/{len(sessions)}] {s['title'][:44]:44s} "
              f"{len(turn_ids):4d} turns | {facts_total:5d} facts, {new_total:5d} new "
              f"| {el/60:.1f}m")
    print(f"\ndone: {facts_total} extracted, {new_total} new memories, "
          f"{(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
