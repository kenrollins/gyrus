"""Consume thalamus source-items into the knowledge tier (ADR-0007/0008).

gyrus PULLS from thalamus (dependency points this way; thalamus knows nothing of
gyrus). Sources split into two classes, which is truer to ADR-0008 than one gate
for all:

- TRUSTED (authored/curated — Ken's own github journals, and later his notes and
  the email he writes): pre-vetted by virtue of being his, so NO front gate and
  NO extract cap. A journal about a brand-new project has nothing similar in
  memory yet and would score LOW on a similarity gate — exactly the novel signal
  we most want to keep. Gating authored content is backwards.
- FIREHOSE (arXiv, podcasts, web): cheap to scan, expensive to extract, so the
  earned-value FRONT GATE applies — only items whose abstract is near what Ken
  ALREADY tracks get the expensive extraction; the rest are skipped by advancing
  the cursor past them (re-scan later if his interests shift).
"""
from __future__ import annotations

import logging
import os

import httpx

from . import db, extraction, gateway
from .config import settings

logger = logging.getLogger(__name__)

THALAMUS_URL = os.environ.get("THALAMUS_URL", "http://10.0.13.14:8000").rstrip("/")

# Authored/curated source types: pre-vetted, bypass the front gate, extract all.
# "email" qualifies because the edge collector (Pip VM pusher) only forwards
# senders on the curated source-profile allowlist — the sender-authority gate
# runs at the edge, not here. Raw unfiltered mail must never get this label.
TRUSTED_SOURCES = {"github", "notes", "conference", "email"}


def _source_key(it: dict) -> str:
    """Canonical origin identity for the independence check in persist():
    a near-dup within the same key is one source repeating itself (a
    newsletter's issues, versions of one repo doc), never corroboration."""
    src, ref = it["source_type"], it["source_ref"]
    if src == "email":
        return f"email:{(it.get('author') or 'unknown').lower()}"   # the newsletter
    if src == "github":
        return f"github:{ref.split(':', 1)[0]}"                     # the repo
    return f"{src}:{ref}"                                           # the document


async def _extract_item(conn, it: dict) -> int:
    """Extract one source item into the knowledge tier, labelled by its real
    source (never hardcoded — a github journal is not an arXiv paper)."""
    src = it["source_type"]
    ref = it["source_ref"]
    author = f" — {it['author']}" if it.get("author") else ""
    label = f"[Source: {src} {ref}{author}]"
    msg = [{"role": "user", "content": f"{label}\n{it['title']}\n\n{it['body']}"}]
    facts = await extraction.extract(msg)
    for f in facts:
        f.tier = "knowledge"                 # source-ingested is knowledge by definition
        f.source_type = src
        if not f.topic:
            f.topic = it.get("topic") or []
    async with conn.transaction():
        return await extraction.persist(
            conn, facts, turn_id=None, session_id=None, source_ref=ref,
            source_key=_source_key(it))


async def _ingest_batch(*, max_extract: int, relevance_floor: float, batch: int) -> dict:
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

    trusted = [it for it in items if it["source_type"] in TRUSTED_SOURCES]
    firehose = [it for it in items if it["source_type"] not in TRUSTED_SOURCES]

    extracted = 0
    selected_firehose: list[dict] = []
    pool = await db.get_pool()

    # Firehose: score each abstract against Ken's existing interests (front gate).
    if firehose:
        vecs = await gateway.embed(
            [f"{it['title']}. {it['body']}"[:6000] for it in firehose])
        scored = []
        async with pool.acquire() as conn:
            for it, v in zip(firehose, vecs):
                pgv = gateway.to_pgvector(v)
                rel = 0.0
                if pgv is not None:
                    rel = await conn.fetchval(
                        "SELECT COALESCE(max(1 - (embedding <=> $1::vector)), 0) FROM memories"
                        " WHERE retired_at IS NULL AND embedding IS NOT NULL"
                        "   AND tier IN ('knowledge','preference','factual')", pgv) or 0.0
                scored.append((rel, it))
        scored.sort(key=lambda x: -x[0])
        selected_firehose = [it for rel, it in scored if rel >= relevance_floor][:max_extract]

    # Trusted: no gate, no cap — extract everything Ken wrote.
    #
    # A gateway outage mid-batch must not advance the cursor, or the items it
    # skipped are never seen again. But it must not throw either: the drain
    # loop reads `error` to stop cleanly, and an exception would 500 the route
    # and discard the stats for everything already persisted. So bail out the
    # same way the thalamus pull failure does — cursor untouched, work already
    # done reported. Re-running re-extracts the items done so far, which
    # dedupe absorbs (hash/cosine), and that is the cheap side of the trade.
    try:
        async with pool.acquire() as conn:
            for it in trusted:
                extracted += await _extract_item(conn, it)
            for it in selected_firehose:
                extracted += await _extract_item(conn, it)
    except gateway.GatewayError as e:
        logger.warning("thalamus ingest: inference unavailable mid-batch, "
                       "cursor held at %d (%d facts already persisted): %s",
                       cursor, extracted, e)
        return {"pulled": len(items), "trusted": len(trusted),
                "firehose_selected": len(selected_firehose),
                "extracted": extracted, "cursor": cursor, "error": str(e)}

    new_cursor = payload["cursor"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ingest_state SET cursor=$1, updated_at=now()"
                           " WHERE source='thalamus'", new_cursor)
    logger.info("thalamus ingest: pulled %d (trusted %d, firehose %d->%d), extracted %d facts, cursor->%d",
                len(items), len(trusted), len(firehose), len(selected_firehose),
                extracted, new_cursor)
    return {"pulled": len(items), "trusted": len(trusted),
            "firehose_selected": len(selected_firehose), "extracted": extracted,
            "cursor": new_cursor}


async def pull_and_ingest(*, max_extract: int = 12, relevance_floor: float = 0.55,
                          batch: int = 100, drain: bool = False) -> dict:
    """One batch by default; drain=True loops until the cursor catches up (used
    to chew through a large first backlog like the initial github pull)."""
    total = {"pulled": 0, "trusted": 0, "firehose_selected": 0, "extracted": 0, "batches": 0}
    while True:
        res = await _ingest_batch(max_extract=max_extract,
                                  relevance_floor=relevance_floor, batch=batch)
        # Fold the batch in BEFORE checking for an error: a gateway outage can
        # now abort part-way with real work already persisted, and
        # `res.update(total)` would have reported that work as zero (total does
        # not include the current batch yet).
        for k in ("pulled", "trusted", "firehose_selected", "extracted"):
            total[k] += res.get(k, 0)
        total["batches"] += 1
        if res.get("cursor") is not None:
            total["cursor"] = res["cursor"]
        if res.get("error"):
            total["error"] = res["error"]
            return total
        if not drain or res.get("pulled", 0) == 0:
            break
    return total
