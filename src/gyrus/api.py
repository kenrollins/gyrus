"""The gyrus HTTP face (M0).

One store, two faces (ADR-0003); this HTTP API is the seam both faces share.
The Hermes provider (provider/gyrus/) is a thin client of these routes
(ADR-0004). M0 scope: capture turns into episodic scratch, serve a trivial
recall. Extraction, ranking, and consolidation arrive in M1/M2.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from . import __version__, db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.migrate()
    yield
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


@app.get("/health")
async def health() -> dict[str, Any]:
    pool = await db.get_pool()
    n = await pool.fetchval("SELECT count(*) FROM episodic_turns")
    return {"ok": True, "version": __version__, "turns_stored": n}


@app.post("/v1/turns", status_code=201)
async def ingest_turn(turn: TurnIn) -> dict[str, Any]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, platform) VALUES ($1, $2)"
            " ON CONFLICT (session_id) DO NOTHING",
            turn.session_id, turn.platform,
        )
        turn_id = await conn.fetchval(
            "INSERT INTO episodic_turns"
            " (session_id, turn_index, platform, user_text, assistant_text, messages, meta)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
            turn.session_id, turn.turn_index, turn.platform,
            turn.user_text, turn.assistant_text,
            json.dumps(turn.messages) if turn.messages is not None else None,
            json.dumps(turn.meta),
        )
    return {"id": turn_id}


@app.get("/v1/prefetch")
async def prefetch(
    session_id: str = Query(default=""),
    q: str = Query(default=""),
) -> dict[str, Any]:
    """M0 trivial recall: prove the injection seam, not relevance.

    Returns the most recent captured exchanges from OTHER sessions (what a
    fresh session can't already see). M1 replaces this with the hybrid ranker
    served from a background cache.
    """
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT session_id, user_text, assistant_text, created_at"
        " FROM episodic_turns WHERE session_id <> $1"
        " ORDER BY created_at DESC LIMIT $2",
        session_id, db.settings.prefetch_recent_limit,
    )
    total = await pool.fetchval("SELECT count(*) FROM episodic_turns")
    if not rows:
        return {"text": "", "total_turns": total}
    lines = ["[gyrus] recent context from earlier sessions:"]
    for r in rows:
        ts = r["created_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        u = " ".join(r["user_text"].split())[:200]
        a = " ".join(r["assistant_text"].split())[:200]
        lines.append(f"- ({ts}Z) user: {u} | assistant: {a}")
    return {"text": "\n".join(lines), "total_turns": total}


@app.post("/v1/sessions/{session_id}/end")
async def end_session(session_id: str) -> dict[str, Any]:
    """Mark a session boundary. M2 turns this into the consolidation enqueue."""
    pool = await db.get_pool()
    await pool.execute(
        "UPDATE sessions SET ended_at = $2 WHERE session_id = $1",
        session_id, datetime.now(timezone.utc),
    )
    return {"ok": True}
