"""Re-check the 1,031 factual->knowledge moves with the context the first
pass lacked: which systems are KEN'S OWN. Baseline-2 found ~15% of the moved
stratum was personal facts wearing world-knowledge clothes ("Hermes version
is v0.17.0"). Only 'personal' verdicts move back (knowledge->factual)."""
import asyncio, json, os
from collections import Counter
import asyncpg
from gyrus import gateway

SYSTEM = """You label memories for a personal-agent memory store owned by Ken.

CONTEXT you must use: the following are KEN'S OWN projects, systems, and
infrastructure — facts about them are PERSONAL, not world knowledge, no matter
how technical they sound: Pip (his AI agent), Hermes (the agent platform it
runs on), gyrus (his memory service), thalamus (his ingestion service),
gemma-forge, signal-forge, kai-core, kai-notes, kai-adk, dell-vendor-intel,
Dell-AITC, dell-knowledge-base, dell-ai-kb, dell-doudna-monitor, zettlekasten,
ising-harness, qaoa-grid-ops, his Obsidian vault / pip-codex, his kaiju GPU
server, shadesmar, his GB10/DGX Spark, his L4 fleet, his lab gateway, his
watchlists, his cron jobs and scripts under ~/.hermes, and his Dell Federal
work products. His employer's internal tools (SalesChat) are also personal.

For each numbered item:
- "personal": a fact about Ken or any of HIS systems/projects above — versions,
  configs, taxonomies, watchlist contents, script behavior, file paths.
- "world": knowledge true regardless of Ken — other organizations' products,
  research results, conference/industry claims, public technology facts.
- "ambiguous": genuinely unclear.
Return ONLY a JSON array: [{"id": <id>, "label": "personal"|"world"|"ambiguous"}]"""

OUT = "/tmp/retier_fix_results.json"

async def main():
    moved = json.load(open("/tmp/retier-applied-2026-08-15.json"))["moved_ids"] \
        if os.path.exists("/tmp/retier-applied-2026-08-15.json") else None
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    if moved is None:
        # container /tmp was wiped; recover the cohort from the DB: rows that
        # are knowledge/conversation and were factual before the sweep — the
        # sweep is the only writer that produced this tier+source combo in bulk
        moved = [r["id"] for r in await conn.fetch("""
            SELECT id FROM memories WHERE tier='knowledge'
              AND source_type='conversation' AND retired_at IS NULL""")]
    rows = await conn.fetch("""SELECT id, fact, entities FROM memories
        WHERE id = ANY($1::bigint[]) AND retired_at IS NULL AND tier='knowledge'
        ORDER BY id""", moved)
    done = {}
    if os.path.exists(OUT):
        done = {int(k): v for k, v in json.load(open(OUT)).items()}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} moved rows live, {len(todo)} to judge", flush=True)
    B = 20
    for i in range(0, len(todo), B):
        batch = todo[i:i+B]
        lines = [f'{r["id"]}: {r["fact"]}' + (f' (entities: {", ".join(r["entities"])})' if r["entities"] else "")
                 for r in batch]
        try:
            objs = await gateway.chat_json(SYSTEM, "Items:\n\n" + "\n".join(lines))
        except gateway.GatewayError:
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
        print(f"batch {i//B+1}/{(len(todo)+B-1)//B}: {len(done)} judged", flush=True)
    print("DONE", Counter(done.values()), flush=True)
    await conn.close()

asyncio.run(main())
