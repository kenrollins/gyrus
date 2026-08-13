# ADR-0008: Earned-value retention — cheap-ingest all, deep-store only what's used

- **Status:** Accepted
- **Date:** 2026-08-13
- **Deciders:** Ken

## Context

Curated sources (ADR-0006) and especially the arXiv firehose (hundreds of
quant-ph / cs.AI / cs.LG papers a day) produce far more material than is worth
keeping at full depth. Ken cannot triage manually at that scale. Full-document
retention in RAGFlow (parse, chunk, embed the whole PDF/transcript) is
expensive and must be reserved for material that proves its worth — but the
decision of *what earns it* cannot be made honestly at ingestion time, sight
unseen.

## Decision

**Gate retention depth on earned demand, using the signal gyrus already
computes.** Three tiers of retention, each promoted only when value is proven:

1. **Light signal** — thalamus normalizes + gyrus extracts abstracts /
   summaries / metadata into the knowledge tier. Cheap, broad, everything.
2. **Distilled memory** — the gyrus knowledge tier, scored by retrieval-demand
   and cross-source corroboration.
3. **Deep source** — full document in RAGFlow, parsed for deep Q&A. Reserved
   for what earned it.

Promotion 1→3 is **automatic and earned**, computed by the dream pass (which
already scores knowledge by demand/recency and already has a promotion
mechanic — this adds a target, not an engine):

- **retrieval-demand** — the item's knowledge was recalled in real use N+ times
  (`memory_retrievals` already logs this) — including human browsing of the
  insights surface, not only Pip's agentic recall (see Consequences).
- **cross-source corroboration** — the same entity/claim surfaced from ≥2
  independent sources.
- **explicit engagement** — Ken followed up on or acted on it.
- **authority boost** — a source Ken flags as high-trust promotes on fewer hits.

gyrus does not call RAGFlow. It **emits a "promotion-worthy" flag** on the
source item; thalamus (the only service that touches sources) performs the
heavy fetch of the full document and hands it to RAGFlow. Roles stay pure:
thalamus acquires (light and, on demand, heavy), gyrus decides, RAGFlow archives.

This is the project thesis applied one level up: keep what earns its keep, at
increasing cost only as value is proven — the same graded-salience / promotion
logic the dream pass uses to graduate patterns toward the procedural tier,
pointed at a different target. It mirrors how the brain moves rehearsed
material into durable storage.

## Consequences

- RAGFlow stays its own project (ADR-0001 "harvest patterns, don't rebuild
  plumbing"). gyrus grows the promotion *signal*; thalamus grows the *heavy
  fetch*; RAGFlow consumes the promoted few. The line with RAGFlow is now
  sharp: RAGFlow holds raw documents that earned depth; gyrus holds distilled
  insight from everything.
- **Human browsing must count as demand.** The highest-value use of the
  knowledge tier may be Ken reading the `/v1/insights` digest, which is not a
  Pip turn and generates no `memory_retrievals` row by default. The insights
  surface MUST log reads as demand, or the promotion signal misses its main
  usage pattern. (Flagged as a first-class requirement, not an afterthought.)
- This is FUTURE: RAGFlow is provisioned-on-paper (`.229`) but not running, and
  promotion depends on the dream pass (M2) actually working on real data, which
  is unproven. ADR-0008 is a design commitment, not a near-term build. It is
  sequenced after the knowledge tier and the dream pass exist and are validated.
- Firehose economics are a real constraint: "cheap-ingest all of arXiv" is
  cheap per item but not cheap in aggregate against a contended shared embedder
  and a two-model union extractor validated only at conversation volume. A
  capacity plan (batch cadence, a lighter single-model extractor for the
  firehose tier, rate limits) is a prerequisite, not an optimization.

## Amendment 1 (2026-08-13) — a front gate for firehose sources

Ken's refinement, resolving the firehose-cost blind spot from the scope review:
for a high-volume source like arXiv, do NOT run full extraction on every item,
and do NOT go purely on-demand either (pure on-demand only finds what you
already know to ask — it misses the blind spot arXiv exists to cover). Instead,
push the earned-value gate to the FRONT of the pipeline as well as the back:

- **0. Metadata scan** — pull title/abstract/authors/categories for the whole
  lane. Near-free: it is just text, no LLM, and thalamus already normalizes.
- **1. Cheap relevance filter** — rank abstracts against Ken's interest profile
  (embedding similarity + keyword; a single small-model pass at most). No union
  extractor. The survivors appear in the `/v1/insights` digest — this is what
  covers the blind spot, cheaply.
- **2. Full extraction** into the knowledge tier — only on items Ken/Pip engage
  with, or that clear a high relevance bar. This is the first promotion.
- **3. RAGFlow** — full document, on earned demand (the original gate).

So extraction (the expensive union pass) is itself a promotion step, not the
default. The abstract is the light-signal tier; the expensive work happens only
as value is proven — the same earned-value logic, applied at both ends. This
makes "watch all of arXiv" economically real: cost scales with what's relevant,
not with what's published.
