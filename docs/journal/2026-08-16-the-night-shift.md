---
id: journal-025-the-night-shift
type: journal
title: "The night shift"
date: 2026-08-16
visibility: public
tags: [band-discriminator, dedupe, store-grading, baseline, validation]
related:
  - adr/0002-tier-by-signal-source
  - adr/0010-extraction-stays-on-the-70b
one_line: "Overnight: the band discriminator shipped after three validation iterations (two of which failed usefully, one against the grader's own truncated instrument) and folded 464 reworded duplicates with zero validated false-folds; the post-cleanup re-grade puts the store at ~70% keep, up from ~41%."
principle: "Validate the judge before the trial, and validate the validator's ground truth too — the 30 hand grades that gated the fold machinery were themselves made on 130-character previews, and one of them was wrong."
---

Two jobs ran while Ken slept: the 0.90–0.93 band discriminator (journal-023's
design task) and the post-cleanup re-grade. Both produced their numbers; the
more valuable output was what the validation loop caught on the way.

## Three iterations, each failing toward the truth

The discriminator's design was fixed in advance — deterministic
token-conflict check first, LLM same-claim judgment second, fold only what
survives — and a 30-pair hand-graded validation set gated it. Iteration one
failed safe but useless: symmetric-difference token matching plus a strict
"learn nothing new" rubric marked 22 of 24 true rewordings as distinct. A
judge that never folds is just the status quo with extra steps.

Iteration two (conflicting-substitution semantics: exclusive tokens on BOTH
sides; a store-keeper's rubric with worked examples; the 70B instead of
flash) reached 20/30 — with one dangerous error: a pair folded that the
hand grades called distinct. An order-swap agreement gate didn't fix it; the
model held its verdict both directions.

Then the error inverted. Pulling the pair's FULL text showed the hand grade
itself was wrong: both facts carried the same seven-setting enumeration, and
the "distinct" call had been made on 130-character previews. The validator's
ground truth had the same defect class as the thing it was validating —
judgment rendered on truncated evidence. Re-graded on full text: the pair is
borderline-same, the fold acceptable, and the corrected validation profile
reads zero dangerous folds with all five confirmed-distinct pairs caught
(three by the token guard, two by the judge).

## The fold, and what stayed

Full run over the 949 live band pairs, double-judged with order swap:

| verdict | pairs |
|---|---|
| same (double-agreed) — folded | 470 (464 net of chain no-ops) |
| distinct by token guard | 154 |
| distinct by judge | 318 |
| unsure — left alone | 7 |

Spot-checks of committed folds are clean rewordings ("stays silent when
there's nothing to do" / "remains silent when there is nothing to prune").
Every fold is a soft-retire with `superseded_by_id`; the verdicts file is in
`tools/store-audit/`. Store: 10,943 → 10,479. The ~50/50 split vindicates
journal-023's refusal to move the threshold: half this band is exactly the
distinct-facts-in-similar-clothes population a lower threshold would have
destroyed.

(Operational scar, recorded: the first launch crashed because the container
rebuilds had wiped /tmp, taking the scan file with it — the second /tmp
casualty in two days. The re-run chained scan and fold into one detached
command. Anything multi-stage in the container should either live on a
mounted volume or run as one process.)

## The store, re-graded: ~41% → ~70%

Baseline-2 (150 rows, seed 0.43, criteria unchanged from journal-020;
full table in `tools/store-audit/GRADING-BASELINE-2.md`): store-weighted
**~70% keep / ~3% wrong-tier / ~27% drop**, against 41/14/45 twenty-four
hours earlier. The three repairs each show up where predicted: github
37→73% (archive purge), factual 5→53% with wrong-tier at zero (re-tier),
preference 50→100% on the sample (v1.3 expiry catches the session-scoped
wants that were baseline-1's drop mass).

Three small defects surfaced for the next pass, none urgent: the re-tier
classifier moved some personal facts the OTHER way (~15% of that stratum —
"Hermes version is v0.17.0" reads as world knowledge if you don't know
Hermes is Ken's agent); the v1-era arxiv lane fabricated "Ken is tracking X"
interest claims from firehose arrivals (cheap targeted sweep); and
completed-task pairs ("remove the stale entry" / "entry removed, warnings
gone") coexist with no closure mechanism until M3's outcome signals exist.

The runway is clear: M3 is next, and for the first time the store under it
is mostly signal.
