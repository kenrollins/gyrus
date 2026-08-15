"""Seeded stratified sampler for store grading — the instrument behind journal-020.

Draws a reproducible sample across tier x source (Postgres setseed, so the
same seed re-draws the SAME rows against an unchanged store — grade the delta
after a cleanup, not a fresh random set). Grading itself is human/LLM work:
mark each row keep / drop / wrong-tier, report rates PER SOURCE, weight by
stratum size for the store-wide figure.

2026-08-15 baseline (seed 0.42, n=153): store-weighted ~41% keep, ~45% drop,
~14% wrong-tier. Per-source table and criteria in journal-020.

    docker cp tools/store-audit/sample_store.py gyrus:/tmp/sample_store.py
    docker exec gyrus python /tmp/sample_store.py > sample.json
"""
import asyncio
import json
import os

import asyncpg

SEED = 0.42
STRATA = [  # (tier, source_type or None=all-of-tier, n)
    ("knowledge", "github", 30), ("knowledge", "email", 25),
    ("knowledge", "industry", 12), ("knowledge", "arxiv", 12),
    ("knowledge", "conversation", 8), ("knowledge", "podcast", 6),
    ("knowledge", "conference", 6),
    ("factual", None, 20), ("procedural", None, 12),
    ("preference", None, 12), ("open_loop", None, 10),
]

COLS = ("id, tier, source_type, source_ref, source_key, provenance, fact,"
        " entities, topic, confidence, corroboration_count, recall_count,"
        " browse_count, created_at::text, extractor")


async def main() -> None:
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    await conn.execute(f"SELECT setseed({SEED})")
    out = []
    for tier, src, n in STRATA:
        if src:
            rows = await conn.fetch(
                f"SELECT {COLS} FROM memories WHERE retired_at IS NULL"
                "  AND tier=$1 AND source_type=$2 ORDER BY random() LIMIT $3",
                tier, src, n)
        else:
            rows = await conn.fetch(
                f"SELECT {COLS} FROM memories WHERE retired_at IS NULL"
                "  AND tier=$1 ORDER BY random() LIMIT $2", tier, n)
        for r in rows:
            d = dict(r)
            d["entities"] = list(d["entities"] or [])
            d["topic"] = list(d["topic"] or [])
            out.append(d)
    print(json.dumps(out, indent=1, default=str))
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
