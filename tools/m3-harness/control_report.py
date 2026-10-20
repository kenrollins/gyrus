#!/usr/bin/env python3
"""ADR-0014: served vs withheld recall — the control comparison.

Reads episodic_turns.meta->'outcome' (written by outcomes.record_turn_outcomes)
and prints, for turns with tool activity, the two arms side by side:
turns, tool failure rate, retries per turn, and the share of turns with any
retry. Run inside the gyrus container (it has the DSN and asyncpg):

    docker exec gyrus python /app/tools/m3-harness/control_report.py [--days 30]

The arms: `served` = turns whose prefetch returned memories; `withheld` =
turns whose prefetch was computed and logged but returned nothing. Turns
with no retrieval rows at all (empty recall, pre-ADR-0014 turns) are a third
column for context. A procedural memory among the logged rows narrows the
comparison to the tier the thesis is about.
"""
import argparse
import asyncio
import os

import asyncpg

Q = """
WITH t AS (
  SELECT id, created_at,
         (meta->'outcome'->>'ok')::int AS ok,
         (meta->'outcome'->>'fail')::int AS fail,
         (meta->'outcome'->>'retries')::int AS retries,
         (meta->'outcome'->>'served')::int AS served,
         (meta->'outcome'->>'withheld')::int AS withheld,
         EXISTS (SELECT 1 FROM memory_retrievals r JOIN memories m ON m.id=r.memory_id
                 WHERE r.turn_id=episodic_turns.id AND m.tier='procedural') AS has_proc
  FROM episodic_turns
  WHERE (meta->'outcome') IS NOT NULL AND created_at > now() - ($1 || ' days')::interval
)
SELECT CASE WHEN withheld > 0 THEN 'withheld' WHEN served > 0 THEN 'served' ELSE 'no-recall' END AS arm,
       has_proc,
       count(*) AS turns,
       count(*) FILTER (WHERE ok + fail > 0) AS tool_turns,
       round(avg(fail::float / NULLIF(ok + fail, 0))::numeric, 3) AS fail_rate,
       round(avg(retries) FILTER (WHERE ok + fail > 0)::numeric, 2) AS retries_per_turn,
       round((count(*) FILTER (WHERE retries > 0))::numeric
             / NULLIF(count(*) FILTER (WHERE ok + fail > 0), 0), 3) AS share_with_retry
FROM t GROUP BY 1, 2 ORDER BY 2 DESC, 1
"""


async def main(days: int) -> None:
    conn = await asyncpg.connect(os.environ["GYRUS_PG_DSN"])
    try:
        rows = await conn.fetch(Q, str(days))
    finally:
        await conn.close()
    print(f"served vs withheld recall, last {days} days (ADR-0014)")
    print(f"{'arm':10} {'proc?':6} {'turns':>6} {'tool':>6} {'fail%':>7} {'retries':>8} {'any-retry':>10}")
    for r in rows:
        print(f"{r['arm']:10} {str(r['has_proc']):6} {r['turns']:>6} {r['tool_turns']:>6}"
              f" {r['fail_rate'] if r['fail_rate'] is not None else '-':>7}"
              f" {r['retries_per_turn'] if r['retries_per_turn'] is not None else '-':>8}"
              f" {r['share_with_retry'] if r['share_with_retry'] is not None else '-':>10}")
    print("\nRead: the claim holds if served < withheld on fail% and retries, on has_proc=True rows,"
          " with enough turns in both arms to matter (tens, not single digits).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    asyncio.run(main(ap.parse_args().days))
