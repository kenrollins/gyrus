---
id: journal-011-when-the-plan-outran-the-proof
type: journal
title: "When the plan outran the proof"
date: 2026-08-13
visibility: public
tags: [methodology, scope, review, discipline]
related:
  - docs/fable-review/04-handoff-queue
  - journal/2026-08-13-the-dream-pass-meets-real-data
one_line: "In a single session gyrus grew from 'port a memory engine' into a multi-service knowledge platform with three new ADRs and a second project — and a deliberate scope review caught that the distinctive contribution had never run and the falsifiable claim had no data, so we stopped adding and went back to prove the core."
principle: "Ambition compounds faster than proof. Periodically stop and ask which load-bearing claim is still untested — then fix the running system and prove the core before building another storey on it."
---

Worth writing down for the version of us that reads this later, because the
mistake it records is the easiest one to make again.

## The drift

The day began with M1 shipped and a clean question: does consolidation work?
By afternoon the project had grown a knowledge tier (ADR-0006), a whole second
service for ingestion (thalamus, ADR-0007), an earned-value promotion path into
RAGFlow with an arXiv firehose behind it (ADR-0008), a `/v1/insights` surface,
and a redrawn eight-milestone plan. Every piece was individually justified.
Together they were a platform being built outward from a core that had never
been switched on.

None of it was wrong. That's what makes the drift dangerous — it isn't bad
decisions, it's *good* decisions accumulating past the point where the thing
underneath them has been proven. The knowledge tier is genuinely useful and
immediately gratifying (it makes Pip helpful in Ken's real work today), which
is precisely why it kept pulling focus from the harder, load-bearing proof.

## The catch

Two reviews, back to back. An independent Fable pass on M1 found two HIGH
issues — a vector index silently returning 28% of the right answers, and ~27%
of the store being domain knowledge with no home — and, quietly, that the M3
credit-assignment seam was sound. Then a deliberate scope review asked the
uncomfortable question: of everything we've designed, which load-bearing claim
is still untested? The answer was the load-bearing one. ADR-0001 calls
outcome-driven consolidation gyrus's distinctive contribution; it had never run
on any data. BRIEF.md says the entire premise is falsified or confirmed by one
curve — procedural tool-success over sessions — and that curve had zero data
points, because the loop that generates them (M3) didn't exist.

We had spec'd milestones M4 through M9 on top of an engine we'd never started.

## The correction

Harden, then prove, then build. Fix the live-broken index (28% → 100% recall,
one line). Then run the dream pass — the distinctive contribution — on the real
2,700-memory store, in dry-run, and look. It sorted worth-keeping above noise
with no supervision (the vault path and the panel roster at the top, bare
definitions and one-off log lines at the bottom). The engine works. The
detailed reckoning is in the previous entry, including the honest asterisk:
it proved the *framework*, not yet the falsifiable claim, because that still
waits on M3's outcome signal.

The knowledge platform is not cancelled — it's sequenced. thalamus, arXiv,
RAGFlow promotion, the insights surface all remain, behind the proof rather
than ahead of it.

## The lesson, stated generally

Building an AI system, the tiers and adapters and faces multiply easily because
each one is reasonable and each one is fun. Proof does not multiply — it has to
be earned one hard measurement at a time, and it's less immediately
gratifying, so it slips. The counter is a habit, not a heroic act: stop on a
cadence, name the claim that everything rests on, and check whether it has
actually been tested on real data. If it hasn't, that is the only work that
matters until it has.

## Related

- [fable-review handoff](../fable-review/04-handoff-queue.md) — the independent pass
- [The dream pass meets real data](2026-08-13-the-dream-pass-meets-real-data.md) — the proof we went back for
