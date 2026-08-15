#!/usr/bin/env python3
"""Drain `episodic_turns.extracted_at IS NULL` through the window extractor.

The repair tool for turns that were written but never extracted — and the
general answer to "the backlog is stuck", replacing the source-driven
`backfill_state_db.py` for anything already IN the episodic tier.

Why this exists (2026-08-15, 465 stranded turns): `backfill_state_db.py`
extracted over windows built from its SOURCE message list and passed
`turn_ids: []`, deferring the stamp to a session-level `/v1/turns/
mark-extracted` at the end of the session. That marking step is skipped
entirely on a resumed run (it only ever collected ids for turns it had just
posted), so a re-run re-extracted every window at full inference cost and
still marked nothing. Nothing else picked them up either — worker.py's
sweeper deliberately excludes `meta->>'backfill' = 'true'` to avoid racing a
live backfill. Stranded forever, silently.

The fix in shape: WINDOWS ARE BUILT FROM THE TURNS THEMSELVES, so every
window carries the real `turn_ids` it covers and `/v1/extract-window` stamps
them in the SAME TRANSACTION that persists the facts. There is no separate
bookkeeping step to lose. Idempotency, resumability and safe-to-run-twice all
fall out of that one property:

  - RESUMABLE: the work list is a query, not a cursor. Restart re-reads it.
  - SAFE TWICE: a stamped turn leaves the query, so a second run finds
    nothing. Facts dedupe by hash/cosine regardless (extraction.persist).
  - CRASH-SAFE: a failed window stamps nothing (the route is atomic), so the
    turns stay pending and the next run retries them.

Turns from the backfill path have `messages` NULL — only user_text and
assistant_text are populated, and turn_index is NULL too — so the message
list is reconstructed here and ordering comes from `id`. See the module note
in backfill_state_db.py: that is the writer's contract, not corruption.

Runs INSIDE the gyrus container (it needs GYRUS_PG_DSN and asyncpg):

  docker cp tools/backfill_pending.py gyrus:/tmp/ && \
    docker exec gyrus python /tmp/backfill_pending.py --dry-run
  docker exec gyrus python /tmp/backfill_pending.py --limit-windows 2   # taste
  docker exec gyrus python /tmp/backfill_pending.py                     # the lot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import asyncpg
import httpx

GYRUS = os.environ.get("GYRUS_URL", "http://127.0.0.1:8000")

# Window sizing. The budget is the real constraint (extraction truncates at
# settings.extract_char_budget = 24000); the turn cap only stops a run of tiny
# turns from making an unwieldy window. Backfilled turns are capped at 4000
# chars per side by the dumper, so one turn can be 8k on its own.
CHAR_BUDGET = 18000
MAX_TURNS = 10
OVERLAP = 1          # trailing turns repeated into the next window FOR CONTEXT


async def fetch_pending(conn, session: str | None) -> dict[str, list[dict]]:
    """The work list: unextracted turns, grouped by session, ordered by id.

    `turn_index` is NULL on every backfilled row, so `id` IS the ordering —
    it is monotonic per the insert loop that wrote them.
    """
    # CRON IS EXCLUDED, as everywhere else: the golden-set probe showed a
    # scheduled job's own prompt extracted as "Ken prefers...". worker.py
    # filters on the live path and backfill_state_db.py filters at the source;
    # a repair tool that skipped the filter would reintroduce exactly the fake
    # memories the other two exist to prevent. Cron turns are left for
    # worker._extract_turn, which stamps them 'skipped: cron source'.
    rows = await conn.fetch(
        "SELECT id, session_id, user_text, assistant_text, platform"
        "  FROM episodic_turns"
        " WHERE extracted_at IS NULL"
        "   AND lower(coalesce(platform, '')) <> 'cron'" +
        (" AND session_id = $1" if session else "") +
        " ORDER BY session_id, id", *([session] if session else []))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["session_id"], []).append(dict(r))
    return out


def to_messages(turns: list[dict]) -> list[dict[str, str]]:
    """Reconstruct the OpenAI-style message list from the flat text columns.

    Empty sides are dropped rather than sent blank: pair_turns() in the
    source backfill emits user-only turns (Ken firing notes rapidly) and
    assistant-only turns (a long reply split across messages), so a blank
    half is normal and would only waste prompt budget.
    """
    msgs: list[dict[str, str]] = []
    for t in turns:
        if (t["user_text"] or "").strip():
            msgs.append({"role": "user", "content": t["user_text"]})
        if (t["assistant_text"] or "").strip():
            msgs.append({"role": "assistant", "content": t["assistant_text"]})
    return msgs


def build_windows(turns: list[dict]) -> list[dict[str, Any]]:
    """Group a session's turns into windows that fit the extraction budget.

    Each window CLAIMS only its own new turns; the overlap turns are carried
    for context but were already claimed by the previous window. Claiming
    them twice would re-extract the same turn under a second turn_id and
    burn inference for facts that dedupe away.
    """
    windows: list[dict[str, Any]] = []
    i = 0
    while i < len(turns):
        chunk: list[dict] = []
        size = 0
        j = i
        while j < len(turns) and len(chunk) < MAX_TURNS:
            t = turns[j]
            cost = len(t["user_text"] or "") + len(t["assistant_text"] or "")
            if chunk and size + cost > CHAR_BUDGET:
                break
            chunk.append(t)
            size += cost
            j += 1
        claim = [t["id"] for t in chunk]
        context = turns[max(0, i - OVERLAP):i]
        windows.append({"turns": context + chunk, "claim": claim, "chars": size})
        i = j
    return windows


async def heartbeat_lease(dsn: str, stop: asyncio.Event, period: float = 120.0) -> None:
    """Hold the backfill lease while this run is alive.

    worker._sweeper skips backfill turns while this row is fresh. Without it
    the sweeper races us by construction: turns stranded long enough to need
    this tool are older than the grace period that would otherwise protect
    them. The lease is short (10 min in the sweeper) and refreshed here, so a
    crash re-exposes the turns rather than stranding them a second time.
    """
    conn = await asyncpg.connect(dsn)
    try:
        while not stop.is_set():
            await conn.execute(
                "INSERT INTO ingest_state (source, updated_at)"
                " VALUES ('backfill_lease', now())"
                " ON CONFLICT (source) DO UPDATE SET updated_at = now()")
            try:
                await asyncio.wait_for(stop.wait(), timeout=period)
            except asyncio.TimeoutError:
                pass
    finally:
        await conn.close()


async def run_window(client: httpx.AsyncClient, session_id: str, w: dict,
                     *, retries: int, backoff: float) -> dict:
    """POST one window, retrying while inference is unavailable.

    503 means the route refused to stamp because no model answered — the turns
    are untouched and the attempt cost nothing, so retrying is free and
    correct. Measured 2026-08-15: litellm-gw was recreated twice inside 15
    minutes during this backfill, so a long run WILL meet a restart; riding it
    out beats failing 40 windows that a 60-second wait would have saved.
    Anything else (a real 500, a malformed request) is not retried.
    """
    body = {"session_id": session_id, "messages": to_messages(w["turns"]),
            "turn_ids": w["claim"]}
    for attempt in range(retries + 1):
        try:
            r = await client.post(f"{GYRUS}/v1/extract-window", json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 503 or attempt == retries:
                raise
            wait = backoff * (2 ** attempt)
            print(f"    inference unavailable, retry {attempt + 1}/{retries} in {wait:.0f}s",
                  file=sys.stderr, flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="plan only, no inference")
    ap.add_argument("--session", help="restrict to one session_id")
    ap.add_argument("--limit-windows", type=int, default=0, help="stop after N windows")
    ap.add_argument("--parallel", type=int, default=1,
                    help="concurrent windows; each already fires 2 models (extract_union)")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between window dispatches — kaiju serves both models")
    ap.add_argument("--retries", type=int, default=4,
                    help="retries per window while inference is unavailable (503)")
    ap.add_argument("--backoff", type=float, default=30.0,
                    help="first retry wait in seconds; doubles each attempt")
    args = ap.parse_args()

    dsn = os.environ["GYRUS_PG_DSN"]
    conn = await asyncpg.connect(dsn)
    try:
        by_session = await fetch_pending(conn, args.session)
        # Reported, not silently skipped: cron turns are excluded from our work
        # list but still count as pending on /health, so a run that leaves
        # `pending` above zero should say why.
        cron_pending = await conn.fetchval(
            "SELECT count(*) FROM episodic_turns WHERE extracted_at IS NULL"
            "   AND lower(coalesce(platform, '')) = 'cron'")
    finally:
        await conn.close()

    total_turns = sum(len(v) for v in by_session.values())
    plan = [(sid, build_windows(turns)) for sid, turns in by_session.items()]
    n_windows = sum(len(w) for _, w in plan)
    print(f"pending: {total_turns} turns in {len(by_session)} sessions "
          f"-> {n_windows} windows", flush=True)
    if cron_pending:
        print(f"  ({cron_pending} cron turns excluded — worker.py stamps those "
              f"'skipped: cron source')", flush=True)
    for sid, ws in plan:
        print(f"  {sid}  {len(by_session[sid]):4d} turns  {len(ws):3d} windows "
              f"(avg {sum(x['chars'] for x in ws) // max(1, len(ws))} chars)", flush=True)
    if args.dry_run or not n_windows:
        return 0

    sem = asyncio.Semaphore(max(1, args.parallel))
    t0 = time.time()
    stats = {"windows": 0, "facts": 0, "new": 0, "turns": 0, "failed": 0}
    dispatched = 0

    # Take the lease before the first window and hold it for the whole run, so
    # the sweeper does not extract these turns per-turn behind our back.
    stop_lease = asyncio.Event()
    lease_task = asyncio.create_task(heartbeat_lease(dsn, stop_lease))

    async with httpx.AsyncClient(timeout=900) as client:
        async def one(sid: str, w: dict, label: str) -> None:
            async with sem:
                # Rate limit at DISPATCH, inside the semaphore: the pause is
                # between calls hitting the gateway, not merely between
                # scheduling them.
                if args.sleep:
                    await asyncio.sleep(args.sleep)
                try:
                    out = await run_window(client, sid, w,
                                           retries=args.retries, backoff=args.backoff)
                except Exception as e:                          # noqa: BLE001
                    # Nothing was stamped (the route is atomic), so these
                    # turns stay on the work list for the next run.
                    stats["failed"] += 1
                    print(f"  {label} FAILED ({type(e).__name__}: {str(e)[:120]}) "
                          f"— {len(w['claim'])} turns stay pending", file=sys.stderr, flush=True)
                    return
                stats["windows"] += 1
                stats["facts"] += out["extracted"]
                stats["new"] += out["new"]
                stats["turns"] += len(w["claim"])
                print(f"  {label} {len(w['claim']):3d} turns | "
                      f"{out['extracted']:3d} facts, {out['new']:3d} new | "
                      f"{stats['turns']}/{total_turns} done, {(time.time()-t0)/60:.1f}m",
                      flush=True)

        tasks = []
        for sid, ws in plan:
            for k, w in enumerate(ws, 1):
                if args.limit_windows and dispatched >= args.limit_windows:
                    break
                dispatched += 1
                tasks.append(one(sid, w, f"[{sid[:20]} {k}/{len(ws)}]"))
            if args.limit_windows and dispatched >= args.limit_windows:
                break
        try:
            await asyncio.gather(*tasks)
        finally:
            # Release promptly on success, failure, or Ctrl-C — a held lease
            # keeps the sweeper off these turns, which is the opposite of what
            # an aborted run wants.
            stop_lease.set()
            await lease_task

    print(f"\ndone: {stats['windows']} windows, {stats['turns']} turns extracted, "
          f"{stats['facts']} facts ({stats['new']} new), {stats['failed']} windows failed, "
          f"{(time.time()-t0)/60:.1f} min", flush=True)
    if stats["failed"]:
        print("re-run to retry the failed windows (their turns are still pending)",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
