---
id: journal-013-the-crown-jewel-turns
type: journal
title: "The crown jewel turns, once, on real data"
date: 2026-08-13
visibility: public
tags: [m3, outcome-signal, credit-assignment, thesis, validation]
related:
  - adr/0001-port-not-rebuild
  - adr/0002-tier-by-signal-source
one_line: "M3's mechanism ran end to end on a real turn — a recalled procedural memory, followed, met failing tools, and the credit engine moved its confidence — proving the falsifiable loop works; then a guard the first cut lacked stopped one noisy turn from trusting that signal too far."
principle: "Proving a mechanism and trusting its output are two different milestones. Show the loop closes on real data; then refuse to act on it until there's enough evidence to be worth acting on."
---

The whole project is named for one claim: that a personal agent's memory can be
consolidated by *outcome* — a memory earns its keep because following it caused a
good result. Everything to here built the stage. This is the entry where the
mechanism actually ran.

## The loop, on a real turn

A live turn — the agent asked to work a queue of issues — recalled six
procedural memories from gyrus: the exact commands for handling skill
candidates. It followed them. Its tools ran. Some succeeded (a skill lookup),
some failed (a script hit a missing file). The turn's own message list carried
all of it, verbatim, because the provider ships tool calls and results untouched.

The outcome-signal writer — the one piece the port always marked "replace per
tier" — read that turn and did the three things the credit engine needs:
established that the memories were *followed* (their text matched what the agent
actually did, by embedding), read that the tools *partly failed* (a 40% success
rate parsed from the tool results), and wrote a graded `outcome_value` back to
each recalled memory. Then the dream pass — unchanged from M2, the ported credit
math — read those outcomes and moved the memories' confidence from 0.97 to 0.26.

That is the crown jewel working. Recall → reuse → run → pass/fail → credit →
the memory is trusted less next time. Outcome-driven consolidation, on the
agent's own real data, not a fixture.

## The guard the first cut lacked

And immediately, the reason it can't be believed yet. That confidence didn't
fall because the *memories* were bad — it fell because one execution errored,
which might be the agent's mistake, not the memory's. A 0.97 → 0.26 swing off a
single turn is not learning; it is overreaction.

gemma-forge knew this: it refused to use the follow-aware signal until a memory
had at least five judged retrievals. The first cut here skipped that guard, and
the swing is exactly what the guard exists to prevent. Adding it back — require
several outcome samples before ground truth overrides the proxy — the override
correctly stops firing: with today's handful of samples, no memory has enough
evidence yet, and confidence holds at the proxy value. The system now says, in
effect, *I have started measuring, and I will not pretend to have learned until
I have.*

That is the honest state of the thesis. The **mechanism** is proven end to end.
The **claim** — that tool-success-on-recall climbs over sessions — is not, and
cannot be, until there is volume: many procedural memories, each recalled and
acted on many times. That needs the agent used, in earnest, which is the one
thing a refactor month hasn't had. The loop that was theoretical is now real and
self-running (outcomes score themselves as turns land); what it needs next is
not more code but more life.

## What this closes, and what it doesn't

Closed: the port's last "replace" item, the seam Fable verified, the mechanism
the whole design was arranged around. gyrus can now, in principle, learn which
of its procedural memories actually work.

Open, and honestly so: the curve. It waits on usage, and usage waits on the
agent being worth using day to day — which points, not coincidentally, at the
knowledge tier and the ingestion lanes that make it useful. The proof and the
usefulness turn out to need each other.

## Related

- [ADR-0001](../adr/0001-port-not-rebuild.md) — the credit engine this fed
- [ADR-0002](../adr/0002-tier-by-signal-source.md) — the thesis, mechanism now proven
- [The dream pass meets real data](2026-08-13-the-dream-pass-meets-real-data.md) — the framework this completes
