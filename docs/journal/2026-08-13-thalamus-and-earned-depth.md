---
id: journal-009-thalamus-and-earned-depth
type: journal
title: "The senses, and letting usage decide what's worth keeping deeply"
date: 2026-08-13
visibility: public
tags: [architecture, thalamus, ingestion, ragflow, arxiv, futures]
related:
  - adr/0006-knowledge-tier-and-source-ingestion
  - adr/0007-thalamus-ingestion-boundary
  - adr/0008-earned-value-retention
one_line: "Two architecture decisions in one session: ingestion becomes its own service (thalamus) feeding gyrus a thin contract, and retention depth is gated on earned demand — cheap-ingest everything, deep-store in RAGFlow only what usage proves worth keeping."
principle: "Don't decide value at ingestion time — you can't, at scale, and you'll guess wrong. Ingest cheap and broad; let the demand signal you already compute promote the few things that earn deeper, costlier retention."
---

Two moves today took gyrus from "a memory service" to "the cortex in a small
nervous system," and the second one is the idea worth remembering.

## The senses get their own body

ADR-0006 pulled curated high-signal sources — the three-day quantum conference,
ranked email, podcasts, and the arXiv lane Ken is blind to — into gyrus as a
knowledge tier. The immediate temptation was to grow an ingestion wing inside
gyrus. Ken named the trap precisely: "I don't want the gyrus project which is
memory focused to get bloated with an ingestion wing," while also wanting a core
ingestion capability Pip and other things could call.

The resolution (ADR-0007) is a service split at the point where the work changes
kind. **thalamus** — named for the brain's sensory relay, the hub that filters
and routes incoming signal to the cortex — does acquisition and normalization:
fetch, transcribe, dedupe, attribute. Its output is a clean "source item" and
nothing else crosses. gyrus does what it already does well: turn items into
tiered, scored memory. The dependency points one way — gyrus knows a contract,
thalamus knows nothing about gyrus — so either can be deleted without breaking
the other, and thalamus is reusable by anything, not a gyrus-private feeder.

## Letting usage decide what's worth keeping deeply

The better idea is the retention gate (ADR-0008). Ken asked the question that
scale forces: arXiv publishes hundreds of quant-ph / cs.AI papers a day, good
content is buried in it, and no human can decide what deserves to be pulled in
full and kept. Deciding at ingestion time is impossible and dishonest — you
haven't read it yet.

So don't decide then. Ingest everything cheap — abstracts, summaries, metadata —
and let the signal gyrus *already computes* do the promoting. A memory that
keeps getting retrieved for real questions, or gets corroborated by a second
independent source, or that Ken engages with, has earned deeper retention: pull
the full document into RAGFlow, where it becomes deep-searchable. Everything
else stays a cheap distilled note and quietly ages out.

This is the project's own thesis, one level up. gyrus exists to keep what earns
its keep instead of drowning in what merely recurred; the same graded-salience
logic that graduates a pattern toward the procedural tier now graduates a
document toward deep storage. Three tiers of keep-ness — light signal, distilled
memory, deep source — each entered only when value is proven. It is also just
how memory works: everything enters cheap and fleeting; rehearsal moves the few
things that matter into durable store.

The honest caveats, recorded so they aren't romanticised away: this is FUTURE.
RAGFlow isn't running. The promotion signal depends on a dream pass that has not
yet consolidated a single memory on real data. "Cheap-ingest all of arXiv" is
cheap per item and expensive in aggregate against one contended embedder. And
the highest-value use of the knowledge tier may be Ken *reading* the insights
digest — a human act that generates no retrieval row unless we make it — so the
demand signal has to count browsing or it will measure the wrong thing. Elegant
on paper; several unproven assumptions underneath. Which is exactly why the next
entry is a scope review, not more building.

## Related

- [ADR-0006](../adr/0006-knowledge-tier-and-source-ingestion.md) — the knowledge tier
- [ADR-0007](../adr/0007-thalamus-ingestion-boundary.md) — the ingestion boundary
- [ADR-0008](../adr/0008-earned-value-retention.md) — earned-value retention
