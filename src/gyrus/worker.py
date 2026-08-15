"""Background extraction. Nothing on the agent's turn path waits for a model.

`sync_turn` must not block Pip, and consolidation must never run mid-turn
(non-negotiables #3/#4). So ingest writes the raw turn and drops the id on an
in-process queue; this worker does the slow part — an LLM call per window,
embeddings, dedupe — out of band.

Deliberately in-process rather than a broker: one service, one consumer, and
a queue that survives nothing. Durability comes from the DATABASE instead —
`episodic_turns.extracted_at IS NULL` is the real work list, so a restart
resumes by scanning, not by replaying a lost queue.
"""

from __future__ import annotations

import asyncio
import logging

from . import db, extraction
from .config import settings

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] | None = None
_tasks: list[asyncio.Task] = []


def enqueue(turn_id: int) -> None:
    if _queue is None:
        return
    try:
        _queue.put_nowait(turn_id)
    except asyncio.QueueFull:
        # Not a loss: the sweeper picks it up from extracted_at IS NULL.
        logger.warning("extraction queue full; turn %s deferred to sweep", turn_id)


async def _extract_turn(turn_id: int) -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, session_id, user_text, assistant_text, messages, platform"
            " FROM episodic_turns WHERE id = $1 AND extracted_at IS NULL", turn_id)
        if row is None:
            return
        # Cron/scheduled output is never a memory: the golden-set probe showed
        # a scheduled job's own prompt extracted as "Ken prefers...". The live
        # path filters here; the backfill filters at the source query.
        if (row["platform"] or "").lower() == "cron":
            await conn.execute("UPDATE episodic_turns SET extracted_at = now(),"
                               " extract_error = 'skipped: cron source' WHERE id = $1", turn_id)
            return
        messages = [{"role": "user", "content": row["user_text"] or ""},
                    {"role": "assistant", "content": row["assistant_text"] or ""}]
    try:
        facts = await extraction.extract_union(messages)
        async with pool.acquire() as conn:
            async with conn.transaction():
                written = await extraction.persist(
                    conn, facts, turn_id=row["id"], session_id=row["session_id"])
                await conn.execute(
                    "UPDATE episodic_turns SET extracted_at = now(), extract_error = NULL"
                    " WHERE id = $1", turn_id)
        logger.info("turn %s: %d facts extracted, %d new", turn_id, len(facts), written)
    except Exception as e:                                  # noqa: BLE001
        logger.exception("extraction failed for turn %s", turn_id)
        async with pool.acquire() as conn:
            # extracted_at stays NULL so the sweeper retries it.
            await conn.execute("UPDATE episodic_turns SET extract_error = $2 WHERE id = $1",
                               turn_id, str(e)[:500])


async def _consumer(name: str) -> None:
    assert _queue is not None
    while True:
        turn_id = await _queue.get()
        try:
            await _extract_turn(turn_id)
        finally:
            _queue.task_done()


async def _sweeper(interval_s: int = 300) -> None:
    """Catch turns the queue never got: restarts, overflow, transient errors."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            pool = await db.get_pool()
            # Backfill turns are covered by the WINDOW path (bigger context,
            # ~6x fewer calls), so skipping them stops the sweeper racing a
            # live backfill and doing the same work per-turn on an already
            # saturated box. But the skip used to be UNCONDITIONAL, and a
            # backfill that dies mid-run leaves its turns matching it forever:
            # 465 turns sat unextracted for three days with no error and no
            # retry, because the one component that would have caught them was
            # told to ignore them (2026-08-15).
            #
            # So the exclusion is now a GRACE PERIOD, not an exemption. A
            # backfill in flight is protected; one that died is eventually
            # swept per-turn — worse context than a window, but the backlog
            # drains and cannot silently rebuild. Run tools/backfill_pending.py
            # to clear a known-stranded backlog properly (windowed) first.
            rows = await pool.fetch(
                "SELECT id FROM episodic_turns WHERE extracted_at IS NULL"
                " AND (COALESCE(meta->>'backfill', 'false') <> 'true'"
                "      OR created_at < now() - ($1 || ' hours')::interval)"
                " ORDER BY created_at LIMIT 50", str(settings.backfill_grace_hours))
            for r in rows:
                enqueue(r["id"])
            if rows:
                logger.info("sweeper re-queued %d unextracted turns", len(rows))
        except Exception:                                   # noqa: BLE001
            logger.exception("sweeper pass failed")


async def _embed_sweeper(interval_s: int = 120, batch: int = 16) -> None:
    """Give vectors to memories that were written while the embedder was busy.

    Embedding is a REPAIRABLE property, not a write-time requirement: hybrid
    retrieval still has keyword and graph legs without it (non-negotiable #2
    cutting in our favour). Under backfill load kaiju queues the small embedder
    behind the 70B/120B extractors and inline calls time out; this catches up
    afterwards instead of losing the vector forever.
    """
    from . import gateway

    while True:
        await asyncio.sleep(interval_s)
        try:
            pool = await db.get_pool()
            rows = await pool.fetch(
                "SELECT id, fact FROM memories WHERE embedding IS NULL"
                " AND retired_at IS NULL ORDER BY id LIMIT $1", batch)
            if not rows:
                continue
            vectors = await gateway.embed([r["fact"] for r in rows])
            done = 0
            async with pool.acquire() as conn:
                for row, vec in zip(rows, vectors):
                    pgvec = gateway.to_pgvector(vec)
                    if pgvec is None:
                        continue
                    await conn.execute(
                        "UPDATE memories SET embedding = $2::vector, updated_at = now()"
                        " WHERE id = $1", row["id"], pgvec)
                    done += 1
            if done:
                logger.info("embed sweeper: vectorized %d memories", done)
        except Exception:                                   # noqa: BLE001
            logger.exception("embed sweeper pass failed")


async def _outcome_sweeper(interval_s: int = 180) -> None:
    """M3: score procedural outcomes for turns with tool activity, offline.

    The reuse->run->pass/fail signal writes itself as live turns land, so the
    dream pass has ground truth to consolidate on without anyone triggering it.
    """
    from . import outcomes
    while True:
        await asyncio.sleep(interval_s)
        try:
            res = await outcomes.score_pending()
            if res.get("outcomes_written"):
                logger.info("outcome sweeper: %s", res)
        except Exception:                                   # noqa: BLE001
            logger.exception("outcome sweeper pass failed")


async def _thalamus_sweeper(interval_s: int = 21600) -> None:
    """Pull new source-items from thalamus into the knowledge tier, front-gated."""
    from . import ingest
    while True:
        await asyncio.sleep(interval_s)
        try:
            res = await ingest.pull_and_ingest()
            if res.get("extracted"):
                logger.info("thalamus ingest: %s", res)
        except Exception:                                   # noqa: BLE001
            logger.exception("thalamus sweeper failed")


async def start(concurrency: int) -> None:
    global _queue
    _queue = asyncio.Queue(maxsize=1000)
    for i in range(max(1, concurrency)):
        _tasks.append(asyncio.create_task(_consumer(f"extract-{i}")))
    _tasks.append(asyncio.create_task(_sweeper()))
    _tasks.append(asyncio.create_task(_embed_sweeper()))
    _tasks.append(asyncio.create_task(_outcome_sweeper()))
    _tasks.append(asyncio.create_task(_thalamus_sweeper()))
    logger.info("extraction worker started (%d consumers)", concurrency)


async def stop() -> None:
    for t in _tasks:
        t.cancel()
    _tasks.clear()
