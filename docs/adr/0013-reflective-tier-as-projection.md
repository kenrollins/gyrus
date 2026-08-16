# ADR-0013: The reflective tier is a projection, not a second store

- **Status:** Accepted
- **Date:** 2026-08-16
- **Deciders:** Ken (standing "keep going" mandate over the TASKS queue)

## Context

The reflective tier (Neo4j at `10.0.13.224`) is the last unbuilt piece of the
original architecture. Three facts gathered before building changed its shape:

1. **gemma-forge never actually used Graphiti.** `graphiti-core` sits in its
   pyproject with zero imports in src/ — the "PORT AS-IS" label in the
   module-lift map pointed at an aspiration, not code. The source-verification
   pass (2026-08-11) had already flagged "Neo4j/Graphiti can be deferred";
   the audit arc's rule applies: port what was measured, not what was declared.
2. **Graphiti's core value is LLM-driven entity/episode extraction — work
   gyrus has already done** by the time a memory exists (extraction pass,
   entities, provenance, event time, reconciler verdicts). Running a second
   extraction stack over extracted facts would duplicate the pipeline's most
   expensive stage to produce a worse copy of what Postgres already holds.
3. **The `.224` graph is empty but scaffolded** with another pipeline's label
   taxonomy (Source/Theme/Person/…, the graph-builder/theme-extractor
   services — zero nodes). gyrus must coexist, not squat on those labels.

## Decision

**The graph is a nightly projection of what the store already knows, plus
derivations only a graph can compute — and the hot path never touches it.**

- **Direct `neo4j` driver**, gyrus-prefixed labels (`GMemory`, `GEntity`) so
  the lab taxonomy keeps its namespace. Secret-file credential convention.
- **Projected nodes/edges** (all MERGE-idempotent, incremental by an
  `updated_at` watermark kept in `ingest_state` under source `graph`):
  - `(:GMemory {id, tier, confidence, event_at, created_at, retired_at})` —
    retired memories INCLUDED: the graph is where bi-temporal history is
    traversable, not hidden behind `retired_at IS NULL` filters.
  - `(:GEntity {name})` from `memory_entities.normalized`.
  - `(GMemory)-[:MENTIONS]->(GEntity)`.
  - `(GMemory)-[:SUPERSEDED_BY]->(GMemory)` — the reconciler's contradiction,
    fold, and loop-resolution verdicts become traversable provenance chains:
    "why does gyrus believe X" has a path-shaped answer.
- **Offline enrichment → fast-read projection** (the ARCHITECTURE §3 rule):
  entity co-occurrence weights are computed IN the graph nightly and the
  top-k related entities per entity are written back to Postgres
  (`entity_relations`), which the retrieval graph-leg reads to expand query
  entities one hop. Recall latency never pays a bolt round-trip.
- **Sync runs in the dream sweeper** after consolidation — offline, capped,
  and skippable: Neo4j down means the projection goes stale and says so in
  the report; recall (Postgres) is unaffected. The tier is an enrichment,
  never a dependency.

## Consequences

- Entity resolution (M6) gets its substrate: alias candidates are visible as
  near-duplicate `GEntity` nodes sharing co-occurrence profiles. v1 ships
  co-occurrence only; alias merging is follow-on work with its own
  validation (the reconciler taught us what un-validated merging costs).
- Graphiti remains adoptable LATER for what it is actually good at
  (temporal episode queries), layered over this projection — nothing here
  forecloses it; nothing waits for it.
- The projection is rebuildable from Postgres at any time (`--full` resync);
  Neo4j holds no truth of record. Deleting the graph loses derived
  relatedness until the next nightly run, nothing else.
