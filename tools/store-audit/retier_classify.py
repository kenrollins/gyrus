"""Classify factual-tier rows: personal-project fact vs world knowledge.

The pre-ADR-0006 backlog put relayed world knowledge in the factual tier,
where the corroboration evaluator scores it (journal-020: ~60% of the tier).
This pass labels every live factual row via the production extraction lane;
apply_retier.py moves the 'world' rows to the knowledge tier.
"""
import asyncio, json, os
from gyrus import gateway
import asyncpg

SYSTEM = """You label memories for a personal-agent memory store owned by Ken.
For each numbered item, decide:
- "personal": a fact about Ken himself, his decisions, preferences, colleagues,
  or his own projects/systems/infrastructure (his repos, scripts, cron jobs,
  notes, agents, servers, files).
- "world": general knowledge that is true regardless of Ken's involvement —
  vendor/product facts, research results, conference or industry claims,
  technology explanations, other organizations' plans.
- "ambiguous": genuinely unclear from the text alone.
Return ONLY a JSON array: [{"id": <id>, "label": "personal"|"world"|"ambiguous"}, ...]
with exactly one entry per input item."""

OUT = "/tmp/retier_results.json"

async def main():
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    rows = await conn.fetch("""SELECT id, fact, entities FROM memories
        WHERE retired_at IS NULL AND tier='factual' ORDER BY id""")
    done = {}
    if os.path.exists(OUT):
        done = {int(k): v for k, v in json.load(open(OUT)).items()}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} factual rows, {len(done)} already labeled, {len(todo)} to go", flush=True)
    BATCH = 20
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i+BATCH]
        lines = [f'{r["id"]}: {r["fact"]}' + (f' (entities: {", ".join(r["entities"])})' if r["entities"] else "")
                 for r in batch]
        try:
            objs = await gateway.chat_json(SYSTEM, "Items:\n\n" + "\n".join(lines))
        except gateway.GatewayError as e:
            print(f"batch {i//BATCH}: gateway error {e}; will retry on next run", flush=True)
            continue
        valid = {r["id"] for r in batch}
        for o in objs:
            try:
                oid, lab = int(o.get("id")), o.get("label")
            except (TypeError, ValueError):
                continue
            if oid in valid and lab in ("personal", "world", "ambiguous"):
                done[oid] = lab
        with open(OUT, "w") as f:
            json.dump(done, f)
        print(f"batch {i//BATCH + 1}/{(len(todo)+BATCH-1)//BATCH}: labeled {len(done)} total", flush=True)
    from collections import Counter
    print("DONE", Counter(done.values()), flush=True)
    await conn.close()

asyncio.run(main())
