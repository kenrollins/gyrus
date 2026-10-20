---
id: journal-036-the-memory-that-cron-made-immortal
type: journal
title: "The memory that cron made immortal"
date: 2026-10-20
visibility: public
tags: [review, consolidation, retrieval, demand-signal, m3, knowledge-tier]
related:
  - adr/0002-tier-by-signal-source
  - adr/0008-earned-value-retention
  - design/ARCHITECTURE
one_line: "Seven weeks unwatched, the service never missed a night — and the five most-recalled memories in the store are a cron job reading its own bookkeeping 354 times each, at confidence 1.00, unevictable, because recall counts as demand for every caller and a single recall makes a memory immune to eviction."
principle: "A demand signal is only as honest as its least discriminating reader. Exclude the automated callers before recall is allowed to count as value, and never make 'ever recalled' a permanent exemption."
---

Ken asked for a review: it had been running a while, nobody had watched it,
was it living up to the promise? The full write-up is
`docs/REVIEW-2026-10-20.md`; this entry is the finding that reframes it.

## What the dashboards said

Everything green. `{"turns":2549,"pending":0,"memories":18310,"unembedded":0}`.
Sixty-eight dream reports, one a night since 2026-08-15, the last at 21:48
yesterday. Graph projection fresh. Zero retired memories served in three
weeks. Yesterday's sweeper fix wrote 175 outcomes on its first passes. If
the review had stopped at the health endpoint it would have said "ship it".

## What the store said

Sorted by `recall_count`, the top of the store is:

| recalls | conf | fact |
|---|---|---|
| 355 | 1.00 | Created cron job named pip-retention-maintenance with job id b4db3f43… |
| 354 | 1.00 | New cron job created: `pip-proactive-review` (Job ID: `79bfcd37912e`… |
| 354 | 1.00 | Created a cron job named pip-proactive-review with Job ID 79bfcd37… |
| 351 | 1.00 | cron.output_retention set to 96 |
| 333 | 1.00 | Cron job runs quietly when there is no new signal and only delivers… |

Of those 1,747 recalls, 1,740 came from `cron_*` sessions. Pip's scheduled
jobs prefetch on the same prompt every run, the prompt mentions cron, the
keyword and entity legs find the cron bookkeeping, and `log_retrievals`
bumps `recall_count` for whoever asked. The dream pass reads `recall_count`
as demand, demand becomes utility, utility becomes confidence. Cron turns
are refused as memory (the golden-set lesson from August); cron *recalls*
were never refused as evidence.

Then the second half. `consolidate.py` retires a low-utility memory only
when `recall_count == 0`. One recall — by a cron job, by a probe, by anyone
— and the memory can never be evicted by utility. The four procedural
memories the M3 harness falsified in August (journal-026, confidence
1.00 → 0.215) are still live at the bottom of last night's report. The
journal's "demotion → eviction closes that over time" was a belief about
the code, not a reading of it.

Measured 2026-10-20 ~00:45 UTC, asyncpg inside the gyrus container against
the Supabase store; 21-day retrieval window: 1,295 of 3,370 rows from
cron sessions.

## The shape of the drift

The August audit found one pattern in eight clothes: a failure produces a
zero and the zero is recorded as an answer. This review found the mirror
image: **a signal is produced by the wrong source and recorded as earned.**

- Cron recalls counted as demand (above).
- Location chatter from the voice satellites: six live, contradictory
  "Ken's home is N miles from <coordinates>" facts, one at 1.00; "Ken's
  phone is back home" recalled 200 times.
- The entity `ken` on 1,657 memories still carries an IDF of 2.4, so
  "Ken's usual bedtime" ranks two arbitrary Ken-facts above the fact
  "Ken's usual bedtime is 10:30". The code comment names the risk; the
  cap was never written.
- Each turn's recall is logged twice — once before the turn, once by the
  provider's warm-up just after it — and the trailing copy is attributed
  to the *next* turn, so outcome scoring judges the previous question's
  memories against this turn's tools, and demand is counted double.
- The static review added its own: the outcome sweeper selects pending
  turns with no ORDER BY and never stamps turns without tool activity, so
  at 200 dead turns (53 today) it will return the same page forever and
  the thesis signal stops again, with `turns_failed: 0`.

And the thesis itself, now that the sweeper runs: since 2026-08-31, 86
followed procedural recalls on 16 memories, one negative. Pip's tools
succeed almost every time, credit saturates at 1.0 after three samples, and
a success rate that starts near 100% has no room to climb. The gemma-forge
curve began at 20%. The claim needs a counterfactual — withheld recall on a
fraction of turns, or retries as the outcome — before volume alone can
prove or kill it.

## What is not wrong

The knowledge tier's noise control held without help: the June newsletter
satire ("SpaceX acquired Cursor for $60 billion", "Mythos and Fable shut
down by the US government") sank to 0.33 and sits in last night's eviction
list. The reconciler folds 30–130 knowledge claims a week. Nothing retired
is ever served. Yesterday's fallback and sweeper fixes are doing exactly
what their commits say.

What the knowledge tier is *for* is the open question: 14,285 live
memories, 78% of the store, most of the 30-day extraction budget, 2% ever
recalled, 16 ever browsed. The "let me SEE the insights" surface has no
reader. That is a decision for Ken, not a bug.

## What changes

Nothing in code this session — the ask was a review. Nine recommendations
are in the review document, ordered. The first two are small and
load-bearing: stop logging cron recalls as demand, and stop treating "ever
recalled" as an eviction exemption. Everything downstream of M3 reads those
two numbers.
