"""Apply the factual-tier reclassification from retier_classify.py results.

'world' rows -> knowledge tier (source_type='conversation', matching the
existing conversation-extracted knowledge rows). 'personal' and 'ambiguous'
stay factual — conservative by design.
"""
import asyncio, json, os
import asyncpg

async def main():
    labels = {int(k): v for k, v in json.load(open("/tmp/retier_results.json")).items()}
    world = sorted(k for k, v in labels.items() if v == "world")
    from collections import Counter
    print("labels:", Counter(labels.values()))
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    # only rows still live and still factual (idempotent, race-safe)
    async with conn.transaction():
        moved = await conn.fetch("""
            UPDATE memories SET tier='knowledge', source_type='conversation', updated_at=now()
            WHERE id = ANY($1::bigint[]) AND retired_at IS NULL AND tier='factual'
            RETURNING id""", world)
    print(f"moved {len(moved)} of {len(world)} world-labeled rows to knowledge")
    with open("/tmp/retier-applied-2026-08-15.json", "w") as f:
        json.dump({"moved_ids": [r["id"] for r in moved],
                   "labels_summary": dict(Counter(labels.values())),
                   "note": "factual->knowledge, source_type=conversation; journal-020 follow-up"}, f)
    for r in await conn.fetch("""SELECT tier, count(*) n FROM memories
        WHERE retired_at IS NULL GROUP BY 1 ORDER BY 2 DESC"""):
        print(f"  {r['tier']:12s} {r['n']}")
    await conn.close()

asyncio.run(main())
