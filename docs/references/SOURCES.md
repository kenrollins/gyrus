# gyrus — sources & provenance

Every borrowed idea, with a path. gyrus stands on three of Ken's own systems
plus the Hermes contract. Read these before reinventing anything.

## gemma-forge — the measured engine (PORT)

`/data/code/gemma-forge` (public: github.com/kenrollins/gemma-forge)

The STIG-remediation harness whose memory subsystem gyrus ports. Read:
- `gemma_forge/dream/pass_.py` (927L) — the dream pass. **Port as-is.** Note
  commit H-01/F-12 already de-STIG'd it (`skill` is a param; reads
  `outcome_value` / `tip_followed_llm` / `tip_followed_emb` from `tip_retrievals`).
- `gemma_forge/memory/eviction.py` — decay/deletion. Port as-is.
- `gemma_forge/memory/retrieval.py` — hybrid ranker. **Adapt** (rule_id →
  Pip entity/keyword tokens). Its docstring documents why vector-only fails.
- `gemma_forge/memory/tip_writer.py` — adapt (retarget schema).
- `gemma_forge/memory/reflector_parser.py` — **replace** (Pip's turn ≠ Reflector).
- `docs/adr/0016-graphiti-neo4j-postgres-memory-stack.md` — the storage design.
- `docs/adr/0019-context-graph-outcome-attribution.md` — graded outcome_value
  (DEF-26) + per-retrieval causal attribution (the crown jewel).

## signal-forge — the non-STIG port PRECEDENT (STUDY)

`kaiju:/data/code/signal-forge`

Ken's investment-thesis system that **already ported gemma-forge's dream pass to
a domain without STIG ground truth**, using a **"shadow book"** (deterministic
market outcome) as the proxy reward. This is the template for gyrus's
procedural-tier signal (a tool's pass/fail = Pip's shadow book). Read:
- `agents/memory/consolidate.py` — a 2nd, de-STIG'd reference implementation of
  the consolidation pass (weekly timer + manual-grade trigger, idempotent via
  `consolidated_at`, markdown report).
- `docs/phase2-memory-consolidation-plan.md` — cites gemma-forge's dream pass +
  DEF-27 (follow-aware signal); tip-firing capture, decision capture (explicit
  link + narrative), "Watch for" tips rank by `confidence · weight`.
- Also the lineage of the portal's Morning Note design tokens.

## openbrain — design patterns HARVESTED (retired)

`kaiju:/data/code/openbrain` (Ken's own build, git, design docs 00–09). Retired
as a system (thin on consolidation) — mined for patterns:
- `docs/03-DATA-SCHEMA.md` — **`open_loops`** (first-class unresolved-thread
  memory — carry over), `memory_entities` (entity_type/value/score),
  `memory_links` (edges), `memories` (embedding + confidence). RLS for
  multi-client.
- `docs/05-MCP-ADAPTER-SPEC.md` + `src/openbrain/mcp/` — the MCP face reference
  (add/search/recent/open_loops, read-write split, request_id logging).
- `src/openbrain/{extractors,embedder}/` — the extract-facts-not-transcripts split.
- The xr7620 `/data/code/openbrain` scaffold was never built and is deleted.

## Hermes — the integration contract (IMPLEMENT AGAINST)

- `MemoryProvider` ABC — `initialize` / `prefetch` / `sync_turn` (abstract);
  `on_session_end` / `on_pre_compress` / `on_session_switch` / `get_tool_schemas`
  / `handle_tool_call` (optional no-ops). Convention discovery; SQLite skeleton
  ships in the Hermes test suite — copy it.
- Hermes already does per-turn capture (SQLite/FTS5, MEMORY.md/USER.md injection,
  background sync, flush-before-compress). gyrus fills the hygiene gap, not capture.
- Docs: hermes-agent.nousresearch.com/docs/user-guide/{configuring-models,configuration}.

## Platform

- `/data/code/dmz/docs/HERMES-INTEGRATION.md` — gyrus is Phase 3 of the wider
  shadesmar→lab integration.
- `/data/code/dmz/docs/design/PIP-MEMORY-ARCHITECTURE.md` — the platform-side
  pointer to this project.
- `/data/code/dmz/ONBOARDING.md` — the tenant contract.

## Zulip — a second ingest source

`10.0.13.240` — Ken's preferred Pip interface. Fully extractable (get-messages
API, official zulip-archive). Its **topic structure is free episodic
organization**. Backfill vs. live-tail is an open question (ARCHITECTURE §9).

## External memory research (context, not dependency)

The field converges where Ken already dug: four-layer cognitive stack + offline
consolidation + Ebbinghaus-style decay + salience pruning. MCP is the settled
transport; the memory *schema* on top is unsettled (OpenMemory/Mem0,
SuperMemory, "Open Memory Protocol"). Keep gyrus's schema our own; stay
MCP-native so we're not betting on any one project surviving.
