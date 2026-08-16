# Consumer-observed findings for the thalamus audit — 2026-08-16

**For the session auditing thalamus.** Written from the gyrus side after
grading gyrus's store (journal-020/021/022, commits `b6543e2`/`52bd0a9`).
Everything here is thalamus's *output as observed downstream* — nothing in
this file implies thalamus should know about gyrus in code; the dependency
direction (ADR-0007) is untouched. The store grading is the evidence base:
153-row stratified sample, rates per source, criteria in gyrus
`docs/journal/2026-08-15-what-the-store-is-actually-worth.md`.

## Per-lane verdicts (thalamus-fed lanes only)

| lane | keep rate downstream | verdict |
|---|---|---|
| arxiv | 83% | best lane; no changes suggested |
| email | 60% | extraction faithful; two fixable defects below |
| github | 37% | one scoping defect dominates; fix below |

(industry/podcast/conference are NOT thalamus lanes — they predate it, no
`source_ref` — so their poor grades say nothing about thalamus.)

## Finding 1 — github lane ships archived and vendored files (the big one)

26% of the github lane's items (1,639 of 6,344 extracted facts, measured by
path) came from `docs/archive/`, `historical/`, `legacy/`, `deprecated/`,
`.claude/` command files, and vendored framework content (BMad personas
etc.). Downstream effect: stale status docs and third-party boilerplate
became "current truth" — a dated migration step, an archived repo's
"environment setup needed for next session", a vendored framework's command
list. This cohort graded ~57% drop and was soft-retired downstream on
2026-08-15 — but **the lane will refill on the next full re-ingest unless the
adapter stops shipping these paths**.

Suggested fix shape (thalamus's call how): path-based exclusion in the
github adapter — default to current docs only (`docs/**` minus
`docs/archive/**`, minus dot-directories, minus known vendored trees), with
archives as an explicit opt-in if ever wanted. The exclusion pattern that
matched cleanly downstream, verified by spot-check with zero false
positives:

```
docs/archive/ | historical | legacy | deprecat | \.claude/ | BMad
```

## Finding 2 — email items: keep `published_at` faithful; it is about to matter

The email lane's biggest downstream defect is temporal: months of backfilled
newsletters (March–August) all became facts dated by *ingest* time, so old
news scores as current. The fix is downstream (gyrus ADR-0011, proposed:
score recency on event time), **but it only works if the source item's
`published_at` faithfully carries the message `Date:` header** for backfill
as well as live pushes. Worth verifying in the audit: that `published_at`
is populated on every email item, is the *message* date (not fetch date),
and survives the edge-collector push path (ADR-0009) unmangled.

Same check applies to arxiv (submission date) and github (commit/mtime —
whatever the adapter can honestly claim).

## Finding 3 — the lens that found everything else

The gyrus audit brief's pattern held everywhere it was pointed: *"a failure
produces an empty or zero result, and that zero gets recorded as a
legitimate answer."* thalamus already fixed one instance independently
(commit `2448aa2`: arxiv 429 silently returning 0 items). Recommended audit
question for every adapter: **what does this adapter do when its upstream is
unavailable (429, timeout, auth expiry, empty feed) — and is that outcome
distinguishable from "source had nothing new"?** A fetch that returns 0
items and a fetch that failed must not look the same in the cursor/state it
records.

## Context numbers (for calibration, not action)

- One day's github ingest became 49% of everything downstream believed —
  the trusted path has no volume governor. Not necessarily thalamus's
  problem (the consumer opted into trust), but if the audit touches batch
  pacing, know that a single lane's full-history backfill dominates
  everything else in one shot.
- No evidence of item-level duplication from thalamus (the downstream
  duplicate problems were all downstream-caused: a blind index era and
  same-source repetition across issues, both handled consumer-side).
