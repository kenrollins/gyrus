# gyrus — Pip's memory

The consolidation engine behind **Pip** (Ken's Hermes agent): outcome-driven
memory that *learns what's worth keeping* instead of accumulating noise. It
ports gemma-forge's measured dream-pass stack into a **Hermes MemoryProvider**,
tiered by where each memory's reward signal comes from.

> The dentate gyrus is where the brain encodes new memories and does *pattern
> separation* — telling similar experiences apart so they don't blur. That is
> this service's job: encode raw turns into durable, distinguishable memory,
> and consolidate the signal out of the noise.

## Read in order (progressive disclosure)

1. **BRIEF.md** — what it is, the claim it proves, why this shape (+ what was rejected)
2. **docs/design/ARCHITECTURE.md** — the full design + the gemma-forge module-lift map
3. **PLAN.md** — milestones in build order (first is demoable from shadesmar)
4. **TASKS.md** — the working checklist
5. **docs/references/SOURCES.md** — where every borrowed idea comes from, with paths
6. **LAB.md** — this project's lab allocation (address, deps, gateway key)

**Platform contract:** `/data/code/dmz/ONBOARDING.md` — follow it, don't copy it.
**How this plugs into Pip:** `/data/code/dmz/docs/HERMES-INTEGRATION.md` (this is Phase 3).

## Stack

- **Postgres** (shared Supabase `10.0.13.220` — be a client, don't grow a rival):
  episodic + semantic tiers, run history.
- **Neo4j + Graphiti** (`10.0.13.224`): reflective / bi-temporal graph tier.
- **Python service**, own `dmz13` address (`.11`, inherited from retired openbrain).
- **Two faces on one store:** a Hermes `MemoryProvider` (always-injected) and an
  **MCP** face (on-demand, for Claude / OpenAI / Gemini).
- **The dream pass** (consolidation) runs offline on a timer, never inline.

## Non-negotiables

1. **Extract facts, don't store transcripts.** Raw turns are episodic scratch.
2. **Hybrid retrieval** (keyword + semantic + graph) — never vector-only. Keyword
   nails technical strings (`Kaiju`, `gemma-forge`); the entity graph often
   matters more than similarity.
3. **Consolidate offline at a natural boundary**, never mid-turn.
4. **Tier by signal source.** Never score a preference as if it had a
   procedural memory's ground truth (ADR-0002). This is the whole thesis.
5. **Inference only via the gateway** (`10.0.13.201`) with the scoped key.
6. **Don't reinvent the proven parts.** gemma-forge's credit assignment and
   signal-forge's shadow-book pattern are measured; port them (ADR-0001).
