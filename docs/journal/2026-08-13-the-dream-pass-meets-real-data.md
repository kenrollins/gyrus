---
id: journal-010-dream-pass-meets-real-data
type: journal
title: "The dream pass meets real data, and mostly earns its name"
date: 2026-08-13
visibility: public
tags: [m2, consolidation, dream-pass, validation, thesis]
related:
  - adr/0001-port-not-rebuild
  - adr/0002-tier-by-signal-source
  - docs/fable-review/04-handoff-queue
one_line: "The distinctive contribution — outcome-driven consolidation — ran for the first time on 2,700 real memories and correctly sorted worth-keeping above noise; but it did so on proxy signals, because the crown-jewel outcome signal still doesn't exist until M3."
principle: "Validate the engine on real data before building on it — but be precise about WHICH claim the run actually tested. A green result on proxy signals is not the same green as the falsifiable one."
---

The scope review's first blind spot was blunt: we had designed five milestones
past the dream pass while the dream pass — the thing ADR-0001 calls gyrus's
distinctive contribution — had never run once, on any data. So before building
further out, we ran it. On the real store: 2,735 memories distilled from five
months of Ken's actual conversations.

## What it did

Dry-run first (the signal-forge discipline — first contact is a report, not a
mutation). The pass scored every live memory and sorted them. The top and the
bottom are the whole story:

**Top, ~0.92–1.0:** the Obsidian vault path, the NQISRC panel roster, Ken's
Dell email, the conference's strategic conclusions, the recurring email-format
preference. Durable, corroborated, personal, or actually-recalled — the things
a memory system exists to keep.

**Bottom, ~0.40:** "PNT stands for Positioning, Navigation, and Timing." "TRL
stands for Technology Readiness Level." "Standardized AI Daily Brief Source.md
into canonical source." "The assistant is awaiting further slides from
Obenland's presentation." Bare definitions, one-off activity-log entries,
transient open-loops. Noise and staleness, correctly at the bottom.

Nobody told it which was which. It sorted Ken's real memory by worth, and by
eye the sort is right. That is the result we came for: the engine distinguishes
signal from noise on real data. It also found **77 near-duplicate clusters**
(the conference note-taking bred them) — F5 confirmed at scale, with real work
for the merge step.

## What it did NOT do, and the honesty that matters

It scored on **proxy signals** — corroboration frequency, retrieval-demand,
provenance, personal-anchor, recency. Not on the crown jewel. The whole premise
(ADR-0002) is outcome-driven credit: a memory earns its keep because *following
it caused a good outcome*. That signal is `outcome_value`, and there are exactly
zero of them in the store, because the loop that writes them is M3. So this run
validated the **consolidation framework and the factual/preference/recency
evaluators** — real and worth having — but it did not test the falsifiable
claim. The green light here is a different green from the one that matters most.

Two more honest edges. **Zero evictions:** the bottom scored 0.40, above the
0.33 retirement line, so nothing was retired on the first pass. Defensible —
don't delete on day one — but it means "stale memories fade" is currently
happening through *confidence-lowering* (they rank lower), not removal; the
eviction threshold is untested because nothing crossed it. And the
**procedural tier had the lowest mean utility (0.518)**, which is itself a
finding: a lot of what the extractor filed as "procedural" is one-off
activity log ("Standardized X", "Executed radar successfully"), not reusable
procedure. That foreshadows a real M3 risk — if Pip's procedural memories are
mostly logs rather than commands-that-get-reused, the falsifiable curve may
have thin data to climb. Worth checking before we build M3, not after.

## Where it leaves us

The distinctive contribution consolidates sensibly on real data. That de-risks
everything downstream — we are no longer building on an unrun engine. But the
run also sharpened what's left to prove: the outcome loop (M3) is still the
crux, and the procedural corpus may be thinner in real reuse-signal than the
count of "procedural" rows suggests. Next: let usage — driven deliberately,
since Ken isn't using Pip during the refactor — generate real outcomes, and
see whether the curve the whole project is named for actually moves.

## Related

- [ADR-0002](../adr/0002-tier-by-signal-source.md) — the thesis this half-tested
- [Five ways a memory system silently forgets](2026-08-12-m1-the-memory-remembers.md)
- [fable-review handoff](../fable-review/04-handoff-queue.md) — F2/F5 closed here
