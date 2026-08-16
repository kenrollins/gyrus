"""The MCP face (ADR-0003, M7) — the store's second face, for every agent
that is not Pip.

Adapted from openbrain's 05-MCP-ADAPTER-SPEC (the harvested reference):
MCP is an adapter; the logic stays in the domain layer, so every tool here
is a thin call into retrieval/extraction/db — the same code paths the
provider face uses. One store, two faces, zero drift.

Spec guardrails carried over:
- read (search/recent/open_loops/insights) and write (add_memory) tools are
  clearly separated, and the write tool goes through extraction.persist —
  embedded, deduped, backpressured like every other write. No side door.
- server-side maximums on every limit arg.
- every call logged with a request_id.

Two deliberate gyrus-isms:
- search_memory logs retrievals under session 'mcp:<request_id>' — an MCP
  search IS demand, and demand is the knowledge tier's earned-value signal
  (ADR-0008). Cross-agent recall feeds the same curve Pip feeds.
- transport auth is the API middleware's bearer token (F3); the face never
  ships open.
"""
from __future__ import annotations

import logging
import uuid

from mcp.server.mcpserver import MCPServer

from . import db, extraction, retrieval

logger = logging.getLogger(__name__)

MAX_LIMIT = 25

mcp = MCPServer("gyrus",
                instructions="Ken's long-term memory (gyrus). Search before "
                             "assuming; write sparingly — extraction quality "
                             "rules apply to you too.")


def http_app():
    """The mountable transport app. Stateless: every /v1-style consumer of
    this face is request-shaped, and state lives in the store, not sessions.

    DNS-rebinding protection is the SDK's browser-attack guard; this face is
    server-to-server on the DMZ behind a bearer token (F3), and its callers
    address it by DMZ IP or lab hostname — so Host allow-listing adds no
    security here and broke every legitimate call (measured: 'Invalid Host
    header' on first deploy). Off, deliberately; the bearer is the boundary.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    return mcp.streamable_http_app(
        streamable_http_path="/", stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False))


def _rid() -> str:
    return uuid.uuid4().hex[:12]


@mcp.tool()
async def search_memory(query: str, limit: int = 5) -> str:
    """Search Ken's long-term memory (hybrid: keyword + semantic + entity
    graph). Returns the most relevant memories with tier and provenance."""
    rid = _rid()
    limit = max(1, min(int(limit), MAX_LIMIT))
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        recalls = await retrieval.search(conn, query, k=limit)
        await retrieval.log_retrievals(conn, recalls, query=query,
                                       session_id=f"mcp:{rid}")
    logger.info("mcp[%s] search_memory(%r) -> %d", rid, query[:60], len(recalls))
    return retrieval.render(recalls) or "No relevant memories."


@mcp.tool()
async def recent_memory(limit: int = 10, tier: str | None = None) -> str:
    """Most recently formed memories, optionally filtered by tier
    (procedural | factual | preference | open_loop | knowledge)."""
    rid = _rid()
    limit = max(1, min(int(limit), MAX_LIMIT))
    if tier is not None and tier not in extraction.TIERS:
        return f"Unknown tier {tier!r}; valid: {', '.join(extraction.TIERS)}"
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT tier, fact, provenance, created_at::date AS d FROM memories"
        " WHERE retired_at IS NULL AND ($1::text IS NULL OR tier = $1)"
        " ORDER BY created_at DESC LIMIT $2", tier, limit)
    logger.info("mcp[%s] recent_memory(tier=%s) -> %d", rid, tier, len(rows))
    return "\n".join(f"({r['tier']}/{r['provenance']}, {r['d']}) {r['fact']}"
                     for r in rows) or "Store is empty."


@mcp.tool()
async def open_loops(limit: int = 10) -> str:
    """Unresolved commitments, questions, and follow-ups — the open_loop
    tier, most recent first, expired ones excluded."""
    rid = _rid()
    limit = max(1, min(int(limit), MAX_LIMIT))
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT fact, created_at::date AS d FROM memories"
        " WHERE retired_at IS NULL AND tier = 'open_loop'"
        "   AND (valid_until IS NULL OR valid_until > now())"
        " ORDER BY created_at DESC LIMIT $1", limit)
    logger.info("mcp[%s] open_loops -> %d", rid, len(rows))
    return "\n".join(f"({r['d']}) {r['fact']}" for r in rows) or "No open loops."


@mcp.tool()
async def insights(source: str | None = None, limit: int = 10) -> str:
    """Browse the knowledge tier (conference/email/github/arXiv distillate)
    by source, newest event first. Browsing here counts as demand and feeds
    retention (ADR-0008)."""
    rid = _rid()
    limit = max(1, min(int(limit), MAX_LIMIT))
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, source_type, fact, coalesce(event_at, created_at)::date AS d"
            " FROM memories WHERE retired_at IS NULL AND tier = 'knowledge'"
            "   AND ($1::text IS NULL OR source_type = $1)"
            " ORDER BY coalesce(event_at, created_at) DESC LIMIT $2", source, limit)
        if rows:
            await conn.execute(
                "UPDATE memories SET browse_count = browse_count + 1,"
                " last_browsed_at = now() WHERE id = ANY($1::bigint[])",
                [r["id"] for r in rows])
    logger.info("mcp[%s] insights(source=%s) -> %d", rid, source, len(rows))
    return "\n".join(f"[{r['source_type']}, {r['d']}] {r['fact']}"
                     for r in rows) or "No knowledge for that source."


@mcp.tool()
async def add_memory(fact: str, tier: str = "factual",
                     entities: list[str] | None = None) -> str:
    """WRITE: store one memory. Goes through the same persist path as
    extraction — embedded, near-dup checked, refused if the embedder is
    down. Provenance is 'assistant_suggested' (an MCP client asserting is
    not Ken asserting)."""
    rid = _rid()
    if tier not in extraction.TIERS:
        return f"Unknown tier {tier!r}; valid: {', '.join(extraction.TIERS)}"
    fact = " ".join(fact.split())
    if len(fact) < 8:
        return "Fact too short to be a memory."
    f = extraction.Fact(tier=tier, fact=fact, entities=entities or [],
                        provenance="assistant_suggested")
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            written = await extraction.persist(
                conn, [f], turn_id=None, session_id=f"mcp:{rid}")
    logger.info("mcp[%s] add_memory(%r) written=%d", rid, fact[:60], written)
    return "Stored." if written else "Folded into an existing memory (near-duplicate)."
