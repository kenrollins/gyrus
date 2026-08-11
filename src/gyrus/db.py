"""asyncpg pool + versioned migrations.

Migrations are plain SQL files in gyrus/migrations/, named NNNN_name.sql,
applied in order inside one transaction each, tracked in schema_migrations.
"""

from __future__ import annotations

import logging
from importlib import resources

import asyncpg

from .config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.pg_dsn, min_size=1, max_size=5, statement_cache_size=0)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrate() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INT PRIMARY KEY, name TEXT NOT NULL,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        files = sorted(
            (f for f in resources.files("gyrus.migrations").iterdir() if f.name.endswith(".sql")),
            key=lambda f: f.name,
        )
        for f in files:
            version = int(f.name.split("_", 1)[0])
            if version in applied:
                continue
            async with conn.transaction():
                await conn.execute(f.read_text())
                await conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)", version, f.name
                )
            logger.info("applied migration %s", f.name)
