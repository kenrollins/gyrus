---
id: journal-015-the-blind-lane-opens
type: journal
title: "The blind lane opens"
date: 2026-08-13
visibility: public
tags: [m5, thalamus, ingestion, arxiv, adr-0007, adr-0008]
related:
  - adr/0007-thalamus-ingestion-boundary
  - adr/0008-earned-value-retention
one_line: "thalamus — the ingestion service — went live and fed gyrus the arXiv lane Ken was blind to: it scanned 100 fresh papers, and gyrus's relevance gate kept exactly the ten in his lane (QAOA, quantum networking, error correction) and extracted them into the knowledge tier, firehose economics solved by the gate rather than by manual triage."
principle: "A firehose is only a problem if you drink all of it. Ingest broad and cheap; let a relevance gate — scored against what the user already tracks — decide the few that earn the expensive step."
---

Ken named a blind spot: hundreds of quantum and AI papers cross arXiv every day,
some of them matter, and no human can triage that. Today the lane opened.

## Two services, one contract

**thalamus** — the ingestion service, its own repo and DMZ tenant (ADR-0007) —
is the lab's sensory relay: it acquires and normalizes high-signal sources into
a single *source-item* contract and serves them over REST. It does no
extraction and no understanding-LLM work; that is the consumer's job. Its first
adapter pulls arXiv metadata (quant-ph, cs.AI, cs.LG) from the public API. The
dependency points one way — gyrus knows thalamus's contract; thalamus knows
nothing of gyrus. Delete either and the other still stands.

**gyrus** is one consumer. It pulls source-items and, crucially, does NOT
extract all of them. arXiv is a firehose — 163 papers in the first fetch — and
the union extractor is expensive. So the earned-value front gate (ADR-0008)
runs first: embed each abstract, score its nearest-neighbour similarity to what
Ken *already* tracks in his knowledge and preference memories, and extract only
the top few above a relevance floor.

## The gate has taste

The first live run scanned 100 papers and kept ten. The ten it kept, by
relevance to Ken's existing memory: QAOA expectation-value hardness, full-stack
quantum networking, Hamiltonian-simulation compilation, transversal-gate
scheduling for decoders, parity mapping for quantum optimization. Exactly his
lane — the papers a quantum-focused field CTO would want flagged — pulled out of
the day's noise without a human reading a single abstract. The other ninety were
scanned for pennies and left unpromoted.

That is the whole ADR-0008 thesis running at the front of the pipeline: cheap to
scan everything, expensive only on what proves relevant. And it composes with
the back of the pipeline — a paper the gate lets in, that Ken then keeps
reaching for, will later earn its full PDF pulled into deep storage.

## What's live, and what's honest

Live and self-running: thalamus fetches arXiv on a timer; gyrus pulls and
front-gates on a timer; the survivors land in the knowledge tier and show up in
the insights surface, browsable by source. The blind lane is a lane now.

Honest edges: the relevance gate is anchored to what Ken already tracks, so it
is good at "more of what he cares about" and blind, by construction, to a
genuinely new field he hasn't touched — a cold-start conservatism worth
revisiting. Email and podcasts are still to come (email has credential gravity
on the agent's host; podcasts need transcription). And the arXiv `body` is the
abstract, not the paper — deep questions wait on the ADR-0008 promotion to
RAGFlow. But the shape is proven: the senses feed the cortex, and the cortex
decides what's worth keeping.

## Related

- [ADR-0007](../adr/0007-thalamus-ingestion-boundary.md) — the ingestion boundary
- [ADR-0008](../adr/0008-earned-value-retention.md) — the front gate this runs
