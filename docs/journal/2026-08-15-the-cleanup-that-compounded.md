---
id: journal-022-the-cleanup-that-compounded
type: journal
title: "The cleanup that compounded"
date: 2026-08-15
visibility: public
tags: [audit, store-repair, retier, dedupe, model-shapes, backpressure]
related:
  - adr/0010-extraction-stays-on-the-70b
  - adr/0011-event-time-grounding
  - adr/0012-model-shape-indirection
one_line: "Executing the audit's repairs in dependency order paid a bonus: re-tiering 1,031 world-knowledge rows turned invisible cross-tier duplicates into foldable same-tier pairs, so the 0.93 merge sweep found 256 merges where the scan had measured 187 — and the store ended the day at 10,966 with every model reference now a shape."
principle: "Order store repairs so each one widens the next one's field of view; a re-tier before a dedupe finds duplicates neither would find alone."
---

The audit (journal-020/021) left four repairs, each gated on a measurement
that now existed. Ken approved the batch; the only real decision left was
order, and order turned out to matter more than expected.

## Retire, then re-tier, then merge

**Retirement first** (it shrinks every later pass): 1,664 github facts whose
`source_ref` matched `docs/archive/`, `historical/`, `legacy`, `deprecated`,
`.claude/`, or `BMad` — the cohort the grading showed at ~57% drop. The
spot-check of every match outside `docs/archive/` found nothing but literal
"X is a deprecated script" facts; zero false positives; soft-retired with the
id list in `tools/store-audit/` for reversal.

**Re-tier second.** The 70B labeled every live factual row personal / world /
ambiguous (92 batches, checkpointed): 1,031 world, 753 personal, 49 ambiguous.
Validated against the hand-graded sample at 12/16 exact agreement with all
four disagreements conservative (rows that stayed factual) — the sweep
under-moves rather than over-moves, which is the right failure direction for
a bulk UPDATE. The world rows went to the knowledge tier as
`source_type='conversation'`, where the recency-based evaluator immediately
rescored them (942 confidences moved down in the next consolidation — the
corroboration evaluator had been flattering them for days).

**Merge last, and the compounding showed up.** The full-store scan had
measured 187 same-tier pairs at ≥0.93. The one-time sweep (the dream pass's
own merge machinery with the backstop at 0.93 for one run) folded **256**.
The extra ~70 were pairs the scan could never see: one member factual, one
knowledge — the same fact extracted once from a conversation and once from a
source, split across tiers by the pre-ADR-0006 era. The re-tier put them in
the same room; the merge then did its job. A dedupe run before the re-tier
would have reported the store cleaner than it was — the same
shape-of-failure this project keeps relearning, dodged this time by sequence
rather than by luck.

Store: 12,886 → **10,966 live** (1,920 retired today, all soft). Health
green, pending 0, unembedded 0.

## The write path now refuses to guess

`persist()` raises `GatewayError` when the embedder returns a vectorless
batch instead of inserting undeduped (the brief's #9, measured at ~10 pairs
of real damage — insurance, not triage, and Ken's ruling either way). Every
caller already treats that as retry-later; `/v1/extract-window` translates it
to a 503. The retrieval path's "a memory with no vector is still a memory"
tolerance is deliberately untouched. Regression test pins the contract.

## Models are now shapes

Ken cleared the key-scope blocker in-session, so ADR-0012 landed whole:
gyrus config names `lab/extract`, `lab/extract-union`, `lab/reason`,
`lab/embed`; the gateway owns the bindings (two new tiers added there, with
the ADR-0010 evidence in a comment at the point of edit); the key keeps the
concrete engine ids so `bench_lanes.py` can still look behind the curtain.
`lab/reason` cost nothing — it was already the fallback's GB10 backend under
a second name, which is the exact two-names-one-backend defect ADR-0010
found in the eval history, now structurally impossible for gyrus. All four
shapes smoke-tested through the gyrus key; the fallback's 900s ceiling rides
on the shape name.

Still open, deliberately: the 0.90–0.93 reworded band (the actual threshold
question), ADR-0011 (event-time grounding, drafted, needs Ken), and the
thalamus-side scoping of the github lane — the retirement cleaned the store,
but the lane will refill with archive facts on its next full re-ingest until
thalamus stops shipping them. That is the other repo's audit session.

The month-out re-grade (same seed, same strata) now has a store worth
measuring against.
