"""Snapshot the M3 curve state — run in-container after each harness phase.

Reports, for every memory the harness touched: confidence, outcome samples,
credit average, and whether it still ranks in its task's recall — the three
observables the curve claim is made of.
"""
import asyncio
import json
import os

import asyncpg


async def main() -> None:
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    rows = await conn.fetch("""
        SELECT m.id, m.tier, left(m.fact, 90) AS fact, m.confidence,
               count(r.outcome_value) AS samples,
               round(avg(r.outcome_value * r.outcome_confidence)::numeric, 3) AS credit,
               count(*) FILTER (WHERE r.followed_llm) AS llm_confirmed
        FROM memory_retrievals r JOIN memories m ON m.id = r.memory_id
        WHERE r.session_id LIKE 'm3-drive%'
        GROUP BY m.id, m.tier, m.fact, m.confidence
        ORDER BY samples DESC, m.id""")
    print(json.dumps([dict(r) for r in rows], indent=1, default=str))
    await conn.close()


asyncio.run(main())
