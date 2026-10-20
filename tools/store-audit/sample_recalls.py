#!/usr/bin/env python3
"""ADR-0014 measurement 2: a grading sheet for recall PRECISION.

Samples N recent served prefetch events (non-cron, non-withheld), one block
per event: the query and the memories that were injected, each with a blank
grade column. Grade each memory R (relevant to the query), H (harmless but
not relevant), or W (wrong / misleading / stale). The relevant share is the
monthly number; W is the one to chase.

    docker exec gyrus python /app/tools/store-audit/sample_recalls.py --n 40 > sheet.md

Write-nothing: this only reads. Keep graded sheets out of git (they quote
Ken's conversations); record the three percentages in the journal.
"""
import argparse
import asyncio
import os

import asyncpg

Q = """
WITH ev AS (
  SELECT session_id, query, date_trunc('second', retrieved_at) AS at
  FROM memory_retrievals
  WHERE NOT withheld AND session_id NOT LIKE 'cron\\_%' AND session_id <> 'review-probe'
    AND retrieved_at > now() - ($2 || ' days')::interval
  GROUP BY 1, 2, 3
  ORDER BY random() LIMIT $1
)
SELECT ev.session_id, ev.query, ev.at, r.rank, m.id, m.tier, m.provenance, m.fact
FROM ev JOIN memory_retrievals r
  ON r.session_id = ev.session_id AND r.query = ev.query
 AND date_trunc('second', r.retrieved_at) = ev.at AND NOT r.withheld
JOIN memories m ON m.id = r.memory_id
ORDER BY ev.at, r.rank
"""


async def main(n: int, days: int) -> None:
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    try:
        rows = await conn.fetch(Q, n, str(days))
    finally:
        await conn.close()
    print(f"# recall precision sheet — {n} events, last {days} days\n")
    print("Grade: R relevant · H harmless · W wrong/stale. Fill the `grade` column.\n")
    last = None
    for r in rows:
        key = (r["session_id"], r["at"])
        if key != last:
            print(f"\n## {r['at']:%Y-%m-%d %H:%M}  `{r['session_id'][:24]}`")
            print(f"**Q:** {r['query'][:300].strip()}\n")
            print("| rank | id | tier/prov | memory | grade |\n|---|---|---|---|---|")
            last = key
        fact = r["fact"].replace("|", "\\|")[:160]
        print(f"| {r['rank']} | {r['id']} | {r['tier']}/{r['provenance']} | {fact} |  |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    asyncio.run(main(a.n, a.days))
