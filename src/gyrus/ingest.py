"""Consume thalamus source-items into the knowledge tier (ADR-0007/0008).

gyrus PULLS from thalamus (dependency points this way; thalamus knows nothing of
gyrus), applies the earned-value FRONT GATE (ADR-0008): a firehose like arXiv is
cheap to scan but not cheap to fully extract, so only abstracts close to what Ken
ALREADY tracks get the expensive union extraction. Relevance = the item
abstract's nearest-neighbour cosine to Ken's existing knowledge/preference
memories — "is this in a lane he cares about?" The rest are left unpulled-again
by advancing the cursor past them; if his interests shift, re-scan later.
"""
from __future__ import annotations

import logging
import os

import httpx

from . import db, extraction, gateway
from .config import settings

logger = logging.getLogger(__name__)

THALAMUS_URL = os.environ.get("THALAMUS_URL", "http://10.0.13.14:8000").rstrip("/")


async def pull_and_ingest(*, max_extract: int = 12, relevance_floor: float = 0.55,
                          batch: int = 100) -> dict:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        cursor = await conn.fetchval(
            "INSERT INTO ingest_state (source) VALUES ('thalamus')"
            " ON CONFLICT (source) DO UPDATE SET source=EXCLUDED.source"
            " RETURNING cursor")

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{THALAMUS_URL}/v1/items",
                            params={"since": cursor, "limit": batch})
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPError as e:
        logger.warning("thalamus pull failed: %s", e)
        return {"pulled": 0, "error": str(e)}

    items = payload["items"]
    if not items:
        return {"pulled": 0, "extracted": 0, "cursor": cursor}

    # Score each item's abstract against Ken's existing interests (front gate).
    vecs = await gateway.embed([f"{it['title']}. {it['body']}"[:6000] for it in items])
    scored = []
    async with pool.acquire() as conn:
        for it, v in zip(items, vecs):
            pgv = gateway.to_pgvector(v)
            rel = 0.0
            if pgv is not None:
                rel = await conn.fetchval(
                    "SELECT COALESCE(max(1 - (embedding <=> $1::vector)), 0) FROM memories"
                    " WHERE retired_at IS NULL AND embedding IS NOT NULL"
                    "   AND tier IN ('knowledge','preference','factual')", pgv) or 0.0
            scored.append((rel, it))
    scored.sort(key=lambda x: -x[0])
    selected = [it for rel, it in scored if rel >= relevance_floor][:max_extract]

    extracted = 0
    async with pool.acquire() as conn:
        for it in selected:
            # One "window" = the paper's title + abstract; extract into knowledge.
            msg = [{"role": "user",
                    "content": f"[Source: arXiv {it['source_ref']} — {it['author']}]\n"
                               f"{it['title']}\n\n{it['body']}"}]
            facts = await extraction.extract(msg)
            for f in facts:
                f.tier = "knowledge"                 # source-ingested is knowledge by definition
                f.source_type = it["source_type"]
                if not f.topic:
                    f.topic = it.get("topic") or []
            async with conn.transaction():
                extracted += await extraction.persist(
                    conn, facts, turn_id=None, session_id=None, source_ref=it["source_ref"])

    new_cursor = payload["cursor"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ingest_state SET cursor=$1, updated_at=now()"
                           " WHERE source='thalamus'", new_cursor)
    logger.info("thalamus ingest: pulled %d, selected %d, extracted %d facts, cursor->%d",
                len(items), len(selected), extracted, new_cursor)
    return {"pulled": len(items), "selected": len(selected), "extracted": extracted,
            "cursor": new_cursor,
            "top": [{"rel": round(r, 3), "ref": it["source_ref"], "title": it["title"][:70]}
                    for r, it in scored[:8]]}
