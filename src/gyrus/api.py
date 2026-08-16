"""The gyrus HTTP face.

One store, two faces (ADR-0003); this HTTP API is the seam both faces share.
The Hermes provider (provider/gyrus/) is a thin client of these routes
(ADR-0004), and the future MCP face wears the same store.

Hot-path contract: `POST /v1/turns` writes and returns — extraction happens
out of band (worker.py). `GET /v1/prefetch` ranks and returns; the provider
calls it from a background thread and serves its own cache to the agent, so
no model call ever sits on Pip's turn path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import __version__, db, retrieval, worker
from .config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.migrate()
    await worker.start(settings.extract_concurrency)
    yield
    await worker.stop()
    await db.close_pool()


app = FastAPI(title="gyrus", version=__version__, lifespan=lifespan)


class TurnIn(BaseModel):
    session_id: str = Field(min_length=1)
    turn_index: int | None = None
    platform: str | None = None
    user_text: str = ""
    assistant_text: str = ""
    # Full OpenAI-style message list for the turn, tool calls untruncated —
    # the M3 causal-attribution judge needs the verbatim action record.
    messages: list[dict[str, Any]] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    # Backfill posts the episodic record faithfully but extracts over WINDOWS
    # (more context per call, ~6x fewer calls than per-turn), so it stores
    # with extract=false and drives /v1/extract-window itself.
    extract: bool = True


class WindowIn(BaseModel):
    session_id: str = Field(min_length=1)
    messages: list[dict[str, Any]]
    turn_ids: list[int] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict[str, Any]:
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT (SELECT count(*) FROM episodic_turns) AS turns,"
        " (SELECT count(*) FROM episodic_turns WHERE extracted_at IS NULL) AS pending,"
        " (SELECT count(*) FROM memories WHERE retired_at IS NULL) AS memories,"
        " (SELECT count(*) FROM memories WHERE retired_at IS NULL AND embedding IS NULL) AS unembedded")
    return {"ok": True, "version": __version__, **dict(row)}


@app.post("/v1/turns", status_code=201)
async def ingest_turn(turn: TurnIn) -> dict[str, Any]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, platform) VALUES ($1, $2)"
            " ON CONFLICT (session_id) DO NOTHING",
            turn.session_id, turn.platform)
        turn_id = await conn.fetchval(
            "INSERT INTO episodic_turns"
            " (session_id, turn_index, platform, user_text, assistant_text, messages, meta)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
            turn.session_id, turn.turn_index, turn.platform,
            turn.user_text, turn.assistant_text,
            json.dumps(turn.messages) if turn.messages is not None else None,
            json.dumps(turn.meta))
    # M3: attach this turn to the memories recalled for it, so the outcome
    # writer can credit the right memories with the turn's tool pass/fail.
    from . import outcomes
    async with pool.acquire() as conn:
        await outcomes.link_retrievals(conn, turn_id, turn.session_id)
    if turn.extract:
        worker.enqueue(turn_id)
    return {"id": turn_id, "queued": turn.extract}


@app.post("/v1/extract-window")
async def extract_window(w: WindowIn) -> dict[str, Any]:
    """Run extraction over a multi-turn window (backfill / session-end path).

    Synchronous by design: the caller is a batch job that wants backpressure,
    not the agent. Nothing on Pip's turn path reaches this route.

    The stamp and the facts share one transaction, so `extracted_at` means
    "extraction ran over this turn" and the route is safe to call twice. That
    only holds if a FAILED pass never stamps: an unreachable gateway used to
    surface as zero facts and mark the turns done anyway, quietly consuming
    the backlog. It now 503s with the turns untouched, so the caller retries.
    """
    from . import extraction
    from .gateway import GatewayError

    # Cron guard, same rule as worker._extract_turn: a scheduled job's output
    # is never a memory. The worker filters on the live path and the backfill
    # filters at its source query; this was the one door with no lock —
    # v1.2's prompt rule alone let cron windows extract 6 and 4 facts on the
    # golden set. Deterministic beats persuasive: refuse the window outright
    # (422, nothing stamped) and let the caller fix its window.
    if w.turn_ids:
        pool = await db.get_pool()
        cron_ids = [r["id"] for r in await pool.fetch(
            "SELECT id FROM episodic_turns WHERE id = ANY($1::bigint[])"
            " AND lower(coalesce(platform, '')) = 'cron'", w.turn_ids)]
        if cron_ids:
            raise HTTPException(
                status_code=422,
                detail=f"window contains cron-platform turns {cron_ids}; "
                       "scheduled output is never extracted (remove them or "
                       "mark them skipped)")

    try:
        facts = await extraction.extract_union(w.messages)
    except GatewayError as e:
        logger.warning("extract-window: inference unavailable, %d turns left pending: %s",
                       len(w.turn_ids), e)
        raise HTTPException(status_code=503, detail=f"inference unavailable: {e}") from e
    # A deadlock here is transient and Postgres expects the loser to retry —
    # but the facts in hand cost a 70B window, so retry the TRANSACTION rather
    # than throwing the inference away. persist() now orders its corroboration
    # bumps to make this rare; this covers what ordering cannot guarantee.
    pool = await db.get_pool()
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    written = await extraction.persist(
                        conn, facts, turn_id=(w.turn_ids[-1] if w.turn_ids else None),
                        session_id=w.session_id)
                    if w.turn_ids:
                        await conn.execute(
                            "UPDATE episodic_turns SET extracted_at = now()"
                            " WHERE id = ANY($1::bigint[])", w.turn_ids)
            break
        except GatewayError as e:
            # persist() refuses to write undeduped when the embedder is down
            # (same contract as the extract call above): the transaction rolled
            # back, the turns are still pending — tell the caller to retry.
            logger.warning("extract-window: embedder unavailable, %d turns left pending: %s",
                           len(w.turn_ids), e)
            raise HTTPException(status_code=503, detail=f"embedder unavailable: {e}") from e
        except asyncpg.exceptions.DeadlockDetectedError:
            if attempt == 2:
                logger.warning("extract-window: deadlock persisted, %d turns left pending",
                               len(w.turn_ids))
                raise
            logger.info("extract-window: deadlock, retrying persist (attempt %d)", attempt + 2)
            await asyncio.sleep(0.5 * (attempt + 1))
    return {"extracted": len(facts), "new": written,
            "facts": [{"tier": f.tier, "fact": f.fact, "provenance": f.provenance}
                      for f in facts]}


class MarkExtracted(BaseModel):
    turn_ids: list[int]


@app.post("/v1/turns/mark-extracted")
async def mark_extracted(m: MarkExtracted) -> dict[str, Any]:
    """Manual escape hatch: declare these turns covered, without extracting.

    NOT the backfill's marking path any more. Marking separately from
    extracting is what stranded 465 turns — a resumed run collected no ids and
    so marked nothing, while re-extracting everything at full cost. Pass real
    `turn_ids` to /v1/extract-window instead and let it stamp them in the same
    transaction as the facts. Use this only to write off turns you have
    decided NOT to extract (junk sessions, known-automated output).
    """
    pool = await db.get_pool()
    await pool.execute(
        "UPDATE episodic_turns SET extracted_at = now()"
        " WHERE id = ANY($1::bigint[]) AND extracted_at IS NULL", m.turn_ids)
    return {"ok": True, "marked": len(m.turn_ids)}


@app.get("/v1/prefetch")
async def prefetch(
    session_id: str = Query(default=""),
    q: str = Query(default=""),
    k: int = Query(default=0, ge=0, le=20),
) -> dict[str, Any]:
    """Hybrid recall for the upcoming turn: keyword + semantic + entity graph."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        recalls = await retrieval.search(conn, q, k=k or None)
        await retrieval.log_retrievals(conn, recalls, query=q, session_id=session_id)
    return {
        "text": retrieval.render(recalls),
        "memories": [{"id": r.memory_id, "tier": r.tier, "fact": r.fact,
                      "provenance": r.provenance, "score": r.score, "legs": r.legs}
                     for r in recalls],
    }


@app.get("/v1/memories")
async def list_memories(
    tier: str = Query(default=""),
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Inspection face: what does gyrus actually believe? (audit, not recall)"""
    pool = await db.get_pool()
    where = ["retired_at IS NULL"]
    args: list[Any] = []
    if tier:
        args.append(tier)
        where.append(f"tier = ${len(args)}")
    if q:
        args.append(q)
        where.append(f"fts @@ websearch_to_tsquery('english', ${len(args)})")
    args.append(limit)
    rows = await pool.fetch(
        f"SELECT id, tier, fact, entities, provenance, confidence, corroboration_count,"
        f" recall_count, source_session_id, created_at FROM memories"
        f" WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ${len(args)}", *args)
    return {"count": len(rows), "memories": [dict(r) for r in rows]}


@app.post("/v1/ingest-thalamus")
async def ingest_thalamus(max_extract: int = Query(default=12, ge=1, le=50),
                          drain: bool = Query(default=False),
                          batch: int = Query(default=100, ge=1, le=200)) -> dict[str, Any]:
    """Pull source-items from thalamus, front-gate for relevance, extract the
    relevant ones into the knowledge tier (ADR-0007/0008). Offline path.

    Smaller `batch` keeps each call short — trusted sources (github journals) are
    large and extract in full, so a big batch can outlast an HTTP timeout."""
    from . import ingest
    return await ingest.pull_and_ingest(max_extract=max_extract, drain=drain, batch=batch)


@app.get("/v1/insights")
async def insights(
    source_type: str = Query(default=""),
    topic: str = Query(default=""),
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=40, ge=1, le=200),
) -> dict[str, Any]:
    """Browse what's being gleaned — the knowledge tier, by source/topic/recency.

    The "let me SEE the insights" surface (ADR-0006). Reading here IS demand
    (ADR-0008: human browsing is the main knowledge-use pattern and must count
    toward promotion), so a browse bumps browse_count on what it returns.
    """
    pool = await db.get_pool()
    where = ["retired_at IS NULL", "tier = 'knowledge'",
             "created_at > now() - ($1 || ' days')::interval"]
    args: list[Any] = [str(days)]
    if source_type:
        args.append(source_type)
        where.append(f"source_type = ${len(args)}")
    if topic:
        args.append(topic.lower())
        where.append(f"${len(args)} = ANY(topic)")
    args.append(limit)
    rows = await pool.fetch(
        f"SELECT id, fact, source_type, source_ref, topic, confidence,"
        f" recall_count, browse_count, created_at FROM memories"
        f" WHERE {' AND '.join(where)}"
        f" ORDER BY created_at DESC LIMIT ${len(args)}", *args)
    if rows:
        await pool.execute(
            "UPDATE memories SET browse_count = browse_count + 1, last_browsed_at = now()"
            " WHERE id = ANY($1::bigint[])", [r["id"] for r in rows])
    facets = await pool.fetch(
        "SELECT source_type, count(*) FROM memories"
        " WHERE retired_at IS NULL AND tier='knowledge' GROUP BY 1 ORDER BY 2 DESC")
    return {"count": len(rows), "by_source": {r["source_type"]: r["count"] for r in facets},
            "insights": [dict(r) for r in rows]}


class Reclassify(BaseModel):
    commit: bool = False


@app.post("/v1/reclassify-knowledge")
async def reclassify_knowledge(r: Reclassify) -> dict[str, Any]:
    """F4 (Fable): move mis-tiered domain facts into the knowledge tier.

    The M1 extractor (pre-M4, no knowledge tier) filed world-knowledge as
    `factual`/`assistant_suggested` with no personal anchor — the RAGFlow-class
    bleed the review flagged. This one-time pass reclassifies them: factual, not
    ken_said, no personal-world term. Dry-run by default. source_type inferred
    from the originating session's title where possible.
    """
    pool = await db.get_pool()
    anchor = "|".join(["ken", "dell", "obsidian", "pip", "hermes", "gyrus", "kaiju", "federal"])
    rows = await pool.fetch(
        "SELECT m.id, m.fact, s.platform, s.session_id FROM memories m"
        " LEFT JOIN sessions s ON s.session_id = m.source_session_id"
        " WHERE m.retired_at IS NULL AND m.tier = 'factual'"
        "   AND m.provenance IN ('assistant_suggested', 'relayed')"
        f"   AND m.fact !~* $1", anchor)
    sample = [{"id": r["id"], "fact": r["fact"][:90]} for r in rows[:15]]
    if r.commit and rows:
        # infer a coarse source_type from the session title/platform
        for row in rows:
            st = "conference" if row["session_id"] and (
                "conference" in (row["session_id"] or "").lower()) else "conversation"
            await pool.execute(
                "UPDATE memories SET tier='knowledge', source_type=COALESCE(source_type,$2),"
                " updated_at=now() WHERE id=$1", row["id"], st)
    return {"committed": r.commit, "candidates": len(rows), "sample": sample}


@app.get("/v1/stats")
async def stats() -> dict[str, Any]:
    pool = await db.get_pool()
    tiers = await pool.fetch(
        "SELECT tier, count(*) AS n, avg(confidence)::float AS avg_conf,"
        " sum(corroboration_count) AS corroborations FROM memories"
        " WHERE retired_at IS NULL GROUP BY tier ORDER BY n DESC")
    prov = await pool.fetch(
        "SELECT provenance, count(*) AS n FROM memories WHERE retired_at IS NULL"
        " GROUP BY provenance ORDER BY n DESC")
    return {"tiers": [dict(r) for r in tiers], "provenance": [dict(r) for r in prov],
            "retrievals": await pool.fetchval("SELECT count(*) FROM memory_retrievals")}


@app.get("/v1/sessions/{session_id}")
async def session_info(session_id: str) -> dict[str, Any]:
    """Turn bookkeeping for a session — lets a resumed backfill skip work."""
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT count(*) AS turns,"
        " count(*) FILTER (WHERE extracted_at IS NULL) AS pending"
        " FROM episodic_turns WHERE session_id = $1", session_id)
    return {"session_id": session_id, **dict(row)}


@app.post("/v1/score-outcomes")
async def score_outcomes(turn_id: int = Query(default=0)) -> dict[str, Any]:
    """M3 outcome-signal writer (offline). Score one turn, or all pending."""
    from . import outcomes
    if turn_id:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            return await outcomes.score_turn(conn, turn_id)
    return await outcomes.score_pending()


@app.post("/v1/consolidate")
async def run_consolidation(commit: bool = Query(default=False)) -> dict[str, Any]:
    """Trigger the dream pass. Dry-run by default; offline, never on a turn path.

    M2 wires this to on_session_end / a timer. For now it's an explicit call so
    the first runs are inspected before anything is committed.
    """
    from . import consolidate
    rep = await consolidate.consolidate(commit=commit, report_dir="/data/dream-reports")
    return {"committed": commit, "scored": rep.scored, "outcome_scored": rep.outcome_scored,
            "confidence_raised": rep.confidence_raised,
            "confidence_lowered": rep.confidence_lowered,
            "evict_candidates": len(rep.evict_candidates),
            "merges": len(rep.merges), "by_tier": rep.by_tier,
            "top": rep.top, "bottom": rep.bottom}


@app.post("/v1/sessions/{session_id}/end")
async def end_session(session_id: str) -> dict[str, Any]:
    """Session boundary. M2 turns this into the consolidation enqueue.

    For now it flushes: any turn in this session the queue missed gets
    extracted rather than waiting for the sweeper.
    """
    pool = await db.get_pool()
    await pool.execute("UPDATE sessions SET ended_at = $2 WHERE session_id = $1",
                       session_id, datetime.now(timezone.utc))
    pending = await pool.fetch(
        "SELECT id FROM episodic_turns WHERE session_id = $1 AND extracted_at IS NULL",
        session_id)
    for r in pending:
        worker.enqueue(r["id"])
    return {"ok": True, "flushed": len(pending)}
