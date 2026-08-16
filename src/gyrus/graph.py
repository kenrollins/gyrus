"""The reflective tier — a nightly graph projection (ADR-0013).

Everything here is derivable from Postgres and MERGE-idempotent; Neo4j holds
no truth of record. The dream sweeper calls sync() after consolidation; a
dead Neo4j makes the projection stale and the report says so — recall never
depends on this module (fast-read projection rule, ARCHITECTURE §3).

Labels are gyrus-prefixed (GMemory/GEntity): the `.224` instance carries
another pipeline's scaffolded taxonomy and namespaces must not collide.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import db
from .config import settings

logger = logging.getLogger(__name__)

RELATED_TOP_K = 8          # per entity, written back to Postgres for the hot leg
SYNC_BATCH = 500


def _password() -> str | None:
    if not settings.neo4j_password_file:
        return None
    try:
        with open(settings.neo4j_password_file) as f:
            return f.read().strip()
    except OSError as e:
        logger.warning("neo4j password file unreadable: %s", e)
        return None


def _driver():
    """None when unconfigured/unreachable — the tier is enrichment, never a
    dependency. Import inside: the neo4j package must not be a hard import
    for callers that never touch the graph (tests, provider path)."""
    pw = _password()
    if not (settings.neo4j_uri and pw):
        return None
    from neo4j import GraphDatabase
    return GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, pw))


@dataclass
class GraphReport:
    memories_synced: int = 0
    mentions_synced: int = 0
    supersedes_synced: int = 0
    entities_related: int = 0
    error: str | None = None


def memory_rows_to_params(rows) -> list[dict]:
    """Row shaping, isolated for tests: timestamps to epoch floats (Neo4j
    driver handles datetimes, but epoch keeps the graph client-agnostic),
    NULLs preserved — an absent event_at must stay absent, not become 0."""
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "tier": r["tier"],
            "confidence": float(r["confidence"]),
            "event_at": r["event_at"].timestamp() if r["event_at"] else None,
            "created_at": r["created_at"].timestamp(),
            "retired_at": r["retired_at"].timestamp() if r["retired_at"] else None,
            "superseded_by": r["superseded_by_id"],
        })
    return out


async def sync(*, full: bool = False) -> GraphReport:
    rep = GraphReport()
    drv = _driver()
    if drv is None:
        rep.error = "neo4j not configured/reachable; projection stale"
        return rep
    pool = await db.get_pool()
    try:
        async with pool.acquire() as conn:
            cursor = 0 if full else (await conn.fetchval(
                "INSERT INTO ingest_state (source) VALUES ('graph')"
                " ON CONFLICT (source) DO UPDATE SET source=EXCLUDED.source"
                " RETURNING cursor") or 0)
            rows = await conn.fetch(
                "SELECT id, tier, confidence, event_at, created_at, retired_at,"
                " superseded_by_id, extract(epoch from updated_at) AS upd"
                " FROM memories WHERE extract(epoch from updated_at) > $1"
                " ORDER BY updated_at LIMIT 20000", float(cursor))
            if not rows:
                return rep
            mentions = await conn.fetch(
                "SELECT memory_id, normalized FROM memory_entities"
                " WHERE memory_id = ANY($1::bigint[])", [r["id"] for r in rows])
        with drv.session() as s:
            s.run("CREATE CONSTRAINT gmem_id IF NOT EXISTS FOR (m:GMemory)"
                  " REQUIRE m.id IS UNIQUE")
            s.run("CREATE CONSTRAINT gent_name IF NOT EXISTS FOR (e:GEntity)"
                  " REQUIRE e.name IS UNIQUE")
            params = memory_rows_to_params(rows)
            for i in range(0, len(params), SYNC_BATCH):
                batch = params[i:i + SYNC_BATCH]
                s.run(
                    "UNWIND $rows AS r MERGE (m:GMemory {id: r.id})"
                    " SET m.tier=r.tier, m.confidence=r.confidence,"
                    "     m.event_at=r.event_at, m.created_at=r.created_at,"
                    "     m.retired_at=r.retired_at", rows=batch)
                rep.memories_synced += len(batch)
                sup = [r for r in batch if r["superseded_by"]]
                if sup:
                    s.run(
                        "UNWIND $rows AS r MATCH (a:GMemory {id: r.id})"
                        " MERGE (b:GMemory {id: r.superseded_by})"
                        " MERGE (a)-[:SUPERSEDED_BY]->(b)", rows=sup)
                    rep.supersedes_synced += len(sup)
            ment = [{"m": r["memory_id"], "e": r["normalized"]} for r in mentions]
            for i in range(0, len(ment), SYNC_BATCH):
                batch = ment[i:i + SYNC_BATCH]
                s.run(
                    "UNWIND $rows AS r MATCH (m:GMemory {id: r.m})"
                    " MERGE (e:GEntity {name: r.e}) MERGE (m)-[:MENTIONS]->(e)",
                    rows=batch)
                rep.mentions_synced += len(batch)
            new_cursor = max(float(r["upd"]) for r in rows)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE ingest_state SET cursor=$1, updated_at=now()"
                " WHERE source='graph'", int(new_cursor))
    except Exception as e:                                  # noqa: BLE001
        rep.error = f"{type(e).__name__}: {e}"
        logger.warning("graph sync failed: %s", rep.error)
    finally:
        drv.close()
    return rep


async def enrich(*, top_k: int = RELATED_TOP_K) -> GraphReport:
    """Compute entity co-occurrence IN the graph; write the top-k related
    entities per entity back to Postgres for the hot retrieval leg."""
    rep = GraphReport()
    drv = _driver()
    if drv is None:
        rep.error = "neo4j not configured; entity_relations stale"
        return rep
    try:
        with drv.session() as s:
            rows = s.run(
                "MATCH (a:GEntity)<-[:MENTIONS]-(m:GMemory)-[:MENTIONS]->(b:GEntity)"
                " WHERE a.name < b.name AND m.retired_at IS NULL"
                " WITH a.name AS ea, b.name AS eb, count(m) AS w WHERE w >= 2"
                " RETURN ea, eb, w").data()
        drv.close()
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("TRUNCATE entity_relations")
                pairs = []
                for r in rows:
                    pairs.append((r["ea"], r["eb"], r["w"]))
                    pairs.append((r["eb"], r["ea"], r["w"]))
                # keep only each entity's top-k, in plain Python (small data)
                by_entity: dict[str, list] = {}
                for e, rel, w in pairs:
                    by_entity.setdefault(e, []).append((w, rel))
                keep = []
                for e, lst in by_entity.items():
                    for w, rel in sorted(lst, reverse=True)[:top_k]:
                        keep.append((e, rel, w))
                await conn.executemany(
                    "INSERT INTO entity_relations (entity, related, weight)"
                    " VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", keep)
                rep.entities_related = len(keep)
    except Exception as e:                                  # noqa: BLE001
        rep.error = f"{type(e).__name__}: {e}"
        logger.warning("graph enrich failed: %s", rep.error)
    return rep
