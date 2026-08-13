# ADR-0006: A knowledge tier for curated high-signal sources, inside gyrus

- **Status:** Accepted
- **Date:** 2026-08-13
- **Deciders:** Ken

## Context

The M1 backfill surfaced that ~27% of the store (the Fable review's F4) is not
memory *about Ken* — it is domain knowledge Pip captured because Ken pointed it
at a high-signal source: three days of quantum-conference note-taking, ranked
email-brief items, and (soon) podcast takeaways. The M1 extractor filed this as
`assistant_suggested` factual memory, where it dilutes the personal-memory
tiers and has no evaluator that would ever score or prune it.

The first instinct (F4's own recommendation) was to scope this out as
"RAGFlow bleeding in." That is wrong. This content is the *product* of
deliberate, directed ingestion — it is high-signal precisely because Ken chose
the source — and it is central to how Pip earns its keep in Ken's Field-CTO
work. The gap is not that the content exists; it is that gyrus has no home for
it, no way to score it honestly, and no way for Ken to *see* what is being
gleaned. Investigation (2026-08-13) also found the capture pipelines already
exist but dead-end: `pip_signal_memory_bridge.py` distills ranked email items
into Obsidian notes plus "OpenBrain-ready candidates" that now flow nowhere
(OpenBrain was retired), and podcast ingestion was never built (dmz Phase-4
`podcast-ingestor`, not running).

## Decision

**Add a `knowledge` tier to gyrus for insights distilled from curated external
sources, and bring the source-ingestion adapters and a visibility surface
inside gyrus.** This is not a new thesis — it is ADR-0002 applied consistently.
ADR-0002 tiers memory *by signal source and scores each with its own
evaluator*. Curated knowledge is simply a fourth signal class:

| Tier | Signal source | Evaluator |
|---|---|---|
| procedural | agentic reuse → tool pass/fail | credit assignment (ADR-0002) |
| factual | contradiction + corroboration | frequency/consistency |
| preference | proxy (corrected/reused/uncontradicted) | weakest proxy |
| **knowledge** | **curated by direction; no outcome** | **source authority × recency × retrieval-demand** |

Design commitments:
- **One store.** The knowledge tier lives in gyrus, retrieved through the same
  hybrid ranker, **down-weighted vs. personal tiers when both match** — a fact
  about Ken outranks a fact about the world. It never enters the M3 procedural
  success metric (the falsifiable claim stays measured on ground-truth tiers).
- **Honest scoring.** Knowledge has no ground truth and no corroboration loop
  (one podcast asserting X is not corroboration). It is scored by source
  authority (a per-source weight Ken controls), recency decay (knowledge goes
  stale on a different clock than a preference), and **retrieval-demand** — did
  it ever answer a real question? That is the only *earned* signal available,
  and it is honest about being a proxy (ADR-0002's discipline).
- **Extraction gate.** The pass must split "Ken teaching me about himself/his
  work" (→ personal tiers) from "Ken directing me to record the world"
  (→ knowledge tier). The existing `relayed` provenance is the seed of this.
- **Visibility is a first-class feature.** Ken must be able to *browse* what is
  being gleaned, by source and topic — not just have it surface reactively in
  recall. A digest surface is part of the deliverable, not an afterthought.
- **Ingestion adapters are thin producers into one endpoint.** Email (reconnect
  the dead `signal_memory_bridge` output), conference/notes (retag the existing
  flow), podcast (new: fetch → transcribe → extract), web (later). Build once.

## Consequences

- The line with RAGFlow sharpens rather than blurs: **gyrus holds the distilled
  insights; RAGFlow (if ever built) holds the raw documents for deep search.**
  ADR-0001's "harvest patterns, don't rebuild plumbing" still holds.
- PLAN.md expands: the back half gains the knowledge tier, the ingestion
  adapters, and the insights surface as explicit milestones (see PLAN).
- The dream pass (M2) must run a per-tier evaluator — recency/demand for
  knowledge, outcome for procedural — which is the shared-framework/plug-in-
  evaluator shape ADR-0002 always implied. M2's schema and eviction generalize
  to cover it.
- Migration debt: the ~710 mislabeled `assistant_suggested` domain facts
  already in the store get reclassified into the knowledge tier by a one-time
  pass, not deleted (they are real, just mis-homed).
- The retired OpenBrain's dangling email-insight pipeline gets a live consumer
  again — this ADR is what closes the leak the OpenBrain cleanup opened.
