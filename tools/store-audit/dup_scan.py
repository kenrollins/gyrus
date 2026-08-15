"""Full-store near-duplicate scan — the instrument behind journal-021.

For every live memory, finds the nearest same-tier neighbour among EARLIER
rows (id <), exact scan (no ANN index — see migration 0003 for why that
matters), and records every pair at cosine >= 0.90. Attributing each pair to
its LATER member is the causal frame: that is the row the write-time dedupe
should have folded.

Run inside the container (needs GYRUS_PG_DSN):

    docker cp tools/store-audit/dup_scan.py gyrus:/tmp/dup_scan.py
    docker exec -d gyrus python /tmp/dup_scan.py        # ~10 min at 12.9k rows
    docker exec gyrus cat /tmp/dup_progress.txt         # poll until DONE

Checkpoints every 1000 rows (/tmp/dup_pairs.partial.json) so a killed run
loses at most a minute. O(n^2) overall — the same scaling note as the dream
pass's exact merge scan (journal-018): fine at ~13k, bound the candidate set
before 3x that.

Measured 2026-08-15 over 12,886 rows: 1,232 pairs >= 0.90, 187 >= 0.93 —
twice, independently, identical results. See dup_classify.py for what they
mean.
"""
import asyncio
import json
import os

import asyncpg

OUT = "/tmp/dup_pairs.json"
PARTIAL = "/tmp/dup_pairs.partial.json"
PROGRESS = "/tmp/dup_progress.txt"
FLOOR = 0.90


async def main() -> None:
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    rows = await conn.fetch(
        "SELECT id, tier, created_at, source_type, source_key, source_ref"
        " FROM memories WHERE retired_at IS NULL AND embedding IS NOT NULL"
        " ORDER BY id")
    out = []
    for i, r in enumerate(rows):
        nn = await conn.fetchrow(
            "SELECT m2.id AS nn_id, 1 - (m2.embedding <=> m1.embedding) AS sim,"
            "       m2.created_at AS nn_created, m2.source_key AS nn_skey,"
            "       m2.source_ref AS nn_sref"
            " FROM memories m1, memories m2"
            " WHERE m1.id = $1 AND m2.id < m1.id AND m2.tier = m1.tier"
            "   AND m2.retired_at IS NULL AND m2.embedding IS NOT NULL"
            " ORDER BY m2.embedding <=> m1.embedding LIMIT 1", r["id"])
        if nn and nn["sim"] is not None and nn["sim"] >= FLOOR:
            out.append({
                "id": r["id"], "tier": r["tier"], "created": str(r["created_at"]),
                "stype": r["source_type"], "skey": r["source_key"],
                "sref": r["source_ref"], "nn_id": nn["nn_id"],
                "sim": float(nn["sim"]), "nn_created": str(nn["nn_created"]),
                "nn_skey": nn["nn_skey"], "nn_sref": nn["nn_sref"],
            })
        if i % 1000 == 0:
            with open(PROGRESS, "w") as f:
                f.write(f"{i}/{len(rows)} flagged={len(out)}\n")
            with open(PARTIAL, "w") as f:
                json.dump(out, f)
    with open(OUT, "w") as f:
        json.dump(out, f)
    with open(PROGRESS, "w") as f:
        f.write(f"DONE {len(rows)} scanned, {len(out)} pairs >= {FLOOR}\n")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
