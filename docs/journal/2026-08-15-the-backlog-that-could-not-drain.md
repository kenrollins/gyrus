---
id: journal-017-the-backlog-that-could-not-drain
type: journal
title: "The backlog that could not drain"
date: 2026-08-15
visibility: public
tags: [m2, extraction, backfill, idempotency, operations, failure-modes]
related:
  - adr/0002-tier-by-signal-source
  - journal/gotchas/empty-extraction-on-dead-gateway-consumes-backlog
  - journal/gotchas/http-driven-model-batch-orphans-work
one_line: "465 turns sat unextracted for three days because the one component that would have retried them had been told to ignore them — and the tool written to drain them nearly erased them instead, because a dead gateway and an empty conversation returned the same value."
principle: "Every exclusion added to a safety net needs an expiry, and every 'fail soft, return empty' needs to know whether its caller is a reader or a writer."
---

`/health` had been reporting `"pending": 465` for three days. Not climbing, not
falling. The turns were in the episodic tier, `extract_error` was NULL on every
one of them, and nothing in the logs complained. They had never been attempted.

The first instinct is to look for the thing that failed. Nothing had. That was
the problem.

## Three components, each behaving correctly

The turns arrived through `backfill_state_db.py`, which imports Hermes's own
capture. It posts each turn with `extract=false` — deliberately, because
extracting per-turn wastes ~6x the model calls that windowing does — and then
drives `/v1/extract-window` itself over windows built from the **source message
list**, passing `turn_ids: []`. Nothing gets stamped by those calls. Instead the
turns are marked at the end of the session, in one `mark-extracted` call, over
the ids the tool collected while posting.

That works exactly once. On a resumed run the tool sees the session already has
turns, posts none, collects no ids — and the marking call it makes at the end is
over an empty list. Meanwhile the windows re-extract the entire session at full
inference cost. The database bears this out: the two stranded sessions have
1,106 memories between them, created across two days of runs, of which 1,024
have `source_turn_id` NULL — facts extracted from turns nobody could attribute
them to. The job ran repeatedly, cost real GPU time, and moved the counter zero.

The safety net should have caught this. `worker.py` runs a sweeper every 300
seconds whose entire purpose is to catch turns the queue missed — restarts,
overflow, transient errors. Its work list is `extracted_at IS NULL`, which these
465 rows matched perfectly. It skipped them all, because of this:

```sql
AND COALESCE(meta->>'backfill', 'false') <> 'true'
```

That line is defensible and was added for a real reason: without it the sweeper
races a running backfill, doing the same work per-turn on an already-saturated
box. But it is written as a permanent property of the rows, not as a statement
about a job that is currently running. A backfill that dies mid-run leaves its
turns matching that predicate forever. The exclusion had no expiry, so the
component whose job was to notice had been instructed not to look.

Three components, none of them broken, and between them a class of work that
could not be finished and could not be seen.

## The fix that nearly did the damage

The repair is straightforward in shape: build the windows from the *turns*
rather than the source messages, so every window carries the real `turn_ids` it
covers and `/v1/extract-window` stamps them in the same transaction that
persists the facts. No separate bookkeeping step means no separate bookkeeping
step to lose. Resumability, idempotency, and safe-to-run-twice all fall out of
that one property instead of being maintained by hand.

I wrote `tools/backfill_pending.py` to do that, ran it against the smaller of
the two sessions — 6 turns, 2 windows — and it finished in 11 seconds reporting
`0 facts, 0 new`. Both windows stamped. `pending` fell by 6.

Eleven seconds is not a plausible time for two windows against a 70B. The logs
had the answer:

```
extract(kaiju/nemotron:70b) attempt 1 failed: All connection attempts failed
extract(kaiju/gpt-oss:120b) attempt 1 failed: All connection attempts failed
extract(vllm/nemotron-120b) attempt 2 failed: All connection attempts failed
INFO: 127.0.0.1:41466 - "POST /v1/extract-window HTTP/1.1" 200 OK
```

`docker ps` explained the cause and indicted the design in the same line:
`litellm-gw   Up 2 minutes`. The gateway had restarted while my run was in
flight. All 8 connection failures in gyrus's entire log history belonged to
those 11 seconds.

The gateway client returns `[]` on any failure — correct, and documented, for
tolerant parsing of models that wrap JSON in fences and thinking blocks. But
`[]` also means "this window contained nothing worth remembering," and
`/v1/extract-window` commits state on that answer. So a routine container
restart produced six turns marked permanently complete, having learned nothing
from them. I restored the six and stopped, because the full run was 465.

The mechanism is written up as
[gotcha-004](gotchas/empty-extraction-on-dead-gateway-consumes-backlog.md). The
line worth keeping here is that the tolerant path was written for the per-turn
worker, which *retries* on an empty result, and was then inherited unchanged by
a batch route that *commits* on one. Same function, same return value, opposite
consequence — and nothing at the boundary marked the transition from reader to
writer.

## What actually changed

- `gateway.chat_json` now tracks whether any candidate lane produced a response,
  and raises `GatewayError` if none did. A model that answered "nothing here"
  still returns `[]`.
- `extract_union` propagates a primary-lane failure and tolerates a
  secondary-lane one — the second opinion is a bonus pass, not a quorum.
- `/v1/extract-window` returns 503 with the turns untouched when inference is
  unavailable, instead of 200 with them stamped.
- The sweeper's backfill exclusion became a **grace period**
  (`backfill_grace_hours`, default 24) rather than an exemption. A backfill in
  flight is still protected; one that died is eventually swept per-turn. Worse
  context than a window, and that is the point — it is a net, not a plan.
- `backfill_state_db.py` windows over turns with real ids, sends `messages` and
  `turn_index` (both were NULL on all 1,825 backfilled rows, which is why the
  M3 attribution judge in `outcomes.py` — it reads `messages` — could not see
  any of them), and hands partially-imported sessions to `backfill_pending.py`
  rather than silently doing nothing at full cost.

## Two more, found only by running it

Draining 465 turns for real surfaced two things no amount of reading would
have:

**The gateway is not stable enough to assume.** `litellm-gw` was recreated
twice inside fifteen minutes during the run (`RestartCount=0` with a fresh
`StartedAt` each time — recreated, not crash-looped). The first time cost six
turns before the 503 fix existed; afterwards it cost five windows that simply
stayed pending. A long model-bound batch *will* meet a restart, so the tool now
retries 503 with exponential backoff instead of merely surviving it. This is
the same lesson as
[gotcha-003](gotchas/http-driven-model-batch-orphans-work.md) from the other
side: there, the client gave up while the server kept working; here, the server
gave up while the client kept asking.

**Two parallel windows deadlock on corroboration.** `persist()` bumped
`corroboration_count` inline, one statement per duplicate, holding each row
lock for the remainder of the transaction. Two windows over the same session
hit the same duplicates in different orders and Postgres shot one of them —
`DeadlockDetectedError`, a whole 70B window's output rolled back. The atomicity
held (nothing stamped, turns stayed pending, no loss), which is the fix from
earlier in this entry doing its job. But it is worth noting *where* this was
lurking: two concurrent windows is exactly `extract_concurrency`'s default, so
the live worker could have hit it too, on a store with enough near-duplicates.
The dedupe rate on this session was ~60%, which is what made it fire so
readily. Bumps are now collected and applied once, in id order — one lock
order every writer agrees on — with a transaction-level retry behind it for
what ordering cannot guarantee.

Both were only reachable by running the thing at real scale against real
infrastructure. The 465 turns were a backlog; they were also the first honest
load test this path has had.

## The part that isn't a code change

Nothing schedules the dream pass. The in-process sweepers cover extraction,
embedding, outcomes, and the thalamus pull, so the store keeps itself current —
but `/v1/consolidate` has never run against real data outside a manual
invocation. `/data/dream-reports` does not exist in the container and there is
no `volumes:` stanza in the compose file; `consolidate()` creates the directory
on demand, so a scheduled run would not fail — it would write its evidence to
container-local disk, which dies with the next `docker compose up --build`.
That is worse than failing, for the same reason the rest of this entry is worth
writing.

That is the same shape as the bug above, one level up. The consolidation pass is
the thesis of this project (ADR-0002), and the thing that would have told us it
wasn't running is a report file nobody had arranged to keep.
