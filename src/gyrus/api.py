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

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query
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
    if turn.extract:
        worker.enqueue(turn_id)
    return {"id": turn_id, "queued": turn.extract}


@app.post("/v1/extract-window")
async def extract_window(w: WindowIn) -> dict[str, Any]:
    """Run extraction over a multi-turn window (backfill / session-end path).

    Synchronous by design: the caller is a batch job that wants backpressure,
    not the agent. Nothing on Pip's turn path reaches this route.
    """
    from . import extraction

    facts = await extraction.extract_union(w.messages)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            written = await extraction.persist(
                conn, facts, turn_id=(w.turn_ids[-1] if w.turn_ids else None),
                session_id=w.session_id)
            if w.turn_ids:
                await conn.execute(
                    "UPDATE episodic_turns SET extracted_at = now() WHERE id = ANY($1::bigint[])",
                    w.turn_ids)
    return {"extracted": len(facts), "new": written,
            "facts": [{"tier": f.tier, "fact": f.fact, "provenance": f.provenance}
                      for f in facts]}


class MarkExtracted(BaseModel):
    turn_ids: list[int]


@app.post("/v1/turns/mark-extracted")
async def mark_extracted(m: MarkExtracted) -> dict[str, Any]:
    """Backfill bookkeeping: these turns were covered by a window extraction."""
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


@app.post("/v1/consolidate")
async def run_consolidation(commit: bool = Query(default=False)) -> dict[str, Any]:
    """Trigger the dream pass. Dry-run by default; offline, never on a turn path.

    M2 wires this to on_session_end / a timer. For now it's an explicit call so
    the first runs are inspected before anything is committed.
    """
    from . import consolidate
    rep = await consolidate.consolidate(commit=commit, report_dir="/data/dream-reports")
    return {"committed": commit, "scored": rep.scored,
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
