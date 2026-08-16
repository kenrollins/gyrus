# Store grading baseline 2 — 2026-08-16, post-cleanup (seed 0.43, n=150)

Same criteria as baseline 1 (journal-020; seed 0.42, graded 2026-08-15
against the pre-cleanup store). New seed because the population changed:
1,920 retirements, 1,031 re-tiers, 279 merges between the two draws.

## Rates per stratum, with baseline-1 comparison

| stratum | n | keep | wrong-tier | drop | baseline-1 keep |
|---|---|---|---|---|---|
| github | 30 | 73% | 0% | 27% | 37% |
| email | 25 | 68% | 0% | 32% | 60% |
| knowledge/conversation | 20 | 70% | 15% | 15% | 100%* |
| industry | 10 | 70% | 0% | 30% | 50% |
| arxiv | 10 | 80% | 0% | 20% | 83% |
| podcast | 4 | 50% | 50% | 0% | 33% |
| conference | 4 | 50% | 25% | 25% | 50% |
| factual | 15 | 53% | 0% | 47% | 5% |
| procedural | 12 | 67% | 0% | 33% | 58% |
| preference | 12 | 100% | 0% | 0% | 50% |
| open_loop | 8 | 50% | 0% | 50% | 60% |
| **total (sample)** | **150** | **69%** | **4%** | **27%** | — |

**Store-weighted: ~70% keep / ~3% wrong-tier / ~27% drop**
(baseline 1: ~41% / ~14% / ~45%).

*baseline-1's knowledge/conversation stratum was 8 rows of fresh live-
conversation extractions; baseline-2's includes the 1,031 re-tiered rows.

## What moved and why

- **github 37%→73%**: the archive/vendored retirement removed the drop mass.
  Remaining drops are link-list/cross-ref scaffolding that predates the v1.1
  source-document rule (e.g. "Related ADRs: [links]") and stale plan ephemera.
- **factual 5%→53% keep, 60%→0% wrong-tier**: the re-tier sweep emptied the
  world-knowledge contamination. Remaining drops are status snapshots
  ("watchdog is paused", "log shows X reconnected") — pre-v1.3 extractions
  with no expiry; they age out via eviction or the next sweep.
- **preference 50%→100%** (n=12, wide CI): baseline-1's drops were
  session-scoped wants; v1.3's expiry inference now catches those at write
  time, and the graded survivors are genuinely durable.
- **email 60%→68%**: same lane, better dates (event_at now real); drops are
  still referent-free headlines and off-profile filler — the ADR-0008-style
  relevance gate for the email lane remains unbuilt.

## New defects surfaced (small, noted for next pass)

1. **Reverse wrong-tier from the re-tier sweep** (~15% of the re-tiered
   stratum, ~180 rows extrapolated): the classifier moved personal facts to
   knowledge when they read as world facts without context ("Hermes version
   is v0.17.0", Ken's own watchlist composition, signal-forge's taxonomy).
   Conservative direction was enforced for personal→knowledge moves only.
2. **Fabricated interest inferences** in the arxiv lane ("Ken is tracking
   research on X", provenance=observed, from firehose arrival) — a v1-prompt
   artifact, ~2/10 of the arxiv sample. Cheap targeted sweep:
   `fact LIKE 'Ken is tracking%' AND source_type='arxiv'`.
3. **Contradiction pairs live simultaneously**: "remove the stale teams
   entry" (procedural) and "no more warnings after removal" (factual) — the
   open_loop/task lifecycle has no closure mechanism until M3/M4 signals.

## Comparison discipline

Baseline-2 is the reference for the ~mid-Sep re-grade. Draw with seed 0.43
against the then-current store, same strata; the honest metric is the keep
delta per stratum, not the memory count.
