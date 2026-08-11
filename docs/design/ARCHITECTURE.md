# gyrus — architecture

The full design. Decisions are ADRs (`docs/adr/`); provenance is
`docs/references/SOURCES.md`; build order is `PLAN.md`.

## 1. The tiers (what kinds of memory exist)

The frontier cognitive stack, same four layers gemma-forge and the serious
2026 memory papers converge on:

| Layer | Holds | Lives in |
|---|---|---|
| **Working** | the current turn / immediate context | the Hermes loop (not gyrus's job) |
| **Episodic** | what happened, per turn/session, + the takeaway | Postgres |
| **Semantic** | distilled durable facts, true across sessions | Postgres (+ a fast-read projection) |
| **Reflective** | relationships, provenance, bi-temporal state | Neo4j + Graphiti |
| **Procedural** | learned skills/patterns — how to act | promoted by the dream pass |

## 2. The thesis: tier by signal source (ADR-0002)

The crux of the whole system. gemma-forge's crown jewel — outcome-driven credit
assignment — needs a reward signal. A personal agent seems to have none. But
Pip's memory splits three ways, each with a *different* signal, and only one is
truly signal-starved:

| Memory tier | Examples | Reward signal | gemma-forge reuse |
|---|---|---|---|
| **Procedural** | a command that worked, a tool quirk, a config fix | **TRUE ground truth** — Pip is agentic: reuse → run tool → pass/fail | credit assignment + causal attribution port **1:1** |
| **Factual** | project facts, entities, who-relates-to-what | contradiction detection + corroboration frequency | structured, weaker than STIG |
| **Preference** | how Ken likes to work | proxy only — corrected? reused? uncontradicted? | weakest; no fakeable ground truth |

**Transfer the machinery, swap the evaluator per tier.** Procedural is the
proof tier — a tool's pass/fail is Pip's "shadow book" (the signal-forge term,
see SOURCES). This is why the port works and why generic memory layers can't:
they never had a ground-truth tier to anchor scoring.

## 3. Storage substrate

- **Postgres** — shared Supabase (`10.0.13.220`), own DB `gyrus`. Episodic +
  semantic + run history. Be a client; don't grow a rival (house rule). pgvector
  for embeddings (verify it builds — the old openbrain gotcha).
- **Neo4j + Graphiti** (`10.0.13.224`) — reflective tier: bi-temporal graph with
  provenance back to source episodes. Adopted primitives; the distinctive work
  is the dream pass on top, not the graph store.
- **Fast-read projection** — a denormalized "current lessons" view the provider's
  `prefetch` reads without touching the graph on the hot path.

## 4. Two faces on one store (ADR-0003)

- **Hermes `MemoryProvider`** (always-injected). The ABC: abstract
  `initialize` / `prefetch` (recall before a turn — MUST return fast from a
  background-populated cache) / `sync_turn` (persist after the response);
  optional no-op hooks `on_session_end`, `on_pre_compress`, `on_session_switch`,
  `get_tool_schemas`, `handle_tool_call`. Convention-based discovery, no Hermes
  core edits; Hermes ships a SQLite provider skeleton to copy.
  - `sync_turn` → episodic ingest (the shape the dream pass already eats).
  - `prefetch` → the retrieval ranker, served from cache.
  - `on_session_end` / `on_pre_compress` → enqueue a consolidation.
  - `get_tool_schemas` / `handle_tool_call` → expose audit/query tools to Pip.
- **MCP server** (on-demand). The same store, for Claude/OpenAI/Gemini. Reuse
  openbrain's already-written adapter spec: `add_memory` / `search_memory` /
  `recent_memory` / `open_loops`, read/write tools separated, every call logged
  with `request_id`. Not v1, but designed for from day one.

Hermes already captures per-turn (SQLite/FTS5, MEMORY.md/USER.md injected,
background sync, a flush before compression). **gyrus does not rebuild capture or
storage** — it fills the exact gap the provider hook exists for: decay, salience,
causal attribution, the entity graph.

## 5. The dream pass (consolidation)

Offline, at a natural boundary (session end / a timer), never mid-turn. Ports
from gemma-forge's 927-line `dream/pass_.py`. What it does each run:

- **Grade salience, not frequency.** First-try win 1.0, 4th+-try 0.5, a memory
  that *broke* something = negative. Solves "500 hits drown 1 good hit."
- **Causal attribution.** For procedural memories: did Pip's actual action
  reflect the retrieved memory, and did the tool succeed? (LLM judge temp 0 +
  embedding check — gemma-forge's `tip_followed` logic, domain-agnostic verbatim.)
- **Decay + eviction** (gemma-forge `memory/eviction.py`, ports as-is).
- **Contradiction reconciliation** (factual tier).
- **Promotion** — patterns that keep earning graduate toward procedural.
- Writes a markdown consolidation report; marks records `consolidated_at`
  (idempotent — the signal-forge pattern).

## 6. The module-lift map (from gemma-forge source, verified 2026-08-10)

The headline: **the hard part ports as-is.** Credit assignment was already
generalized off STIG (commit H-01/F-12 — `skill` is a parameter; the credit math
reads `outcome_value`/`tip_followed_*` from a `tip_retrievals` table, it does NOT
call the OSCAP scanner). Signal *production* and *consumption* are already
separated. Only two real work items remain.

| gemma-forge module | Disposition | Note |
|---|---|---|
| `dream/pass_.py` (927L) — credit assignment | **PORT AS-IS** | skill-parameterized; consumes outcome from a table |
| `memory/eviction.py` — decay/deletion | **PORT AS-IS** | generic; table names parameterized |
| Graphiti/Neo4j + Postgres schema | **PORT AS-IS** | substrate |
| `memory/retrieval.py` — hybrid ranker | **ADAPT** | swap the `rule_id` tokenization branch for Pip's entity/keyword tokens |
| `memory/tip_writer.py` | **ADAPT** | retarget schema/table |
| `memory/reflector_parser.py` | **REPLACE** | Pip's turn shape ≠ gemma-forge's Reflector output; keep the pattern, rewrite the parser |
| **the outcome-signal writer** (populates `tip_retrievals.outcome_value`) | **REPLACE per tier** | this IS the "swap the evaluator" job — cleanly isolated by the schema |

**Net: two work items** — (1) the per-tier outcome-signal writers, (2) the
turn-extraction parser. Everything else port-or-adapt.

## 7. Retrieval (hybrid, non-negotiable)

Keyword (BM25/FTS) + semantic (embeddings) + graph (entity/relation), fused.
Keyword nails technical strings (`Kaiju`, `gemma-forge`); the entity graph often
matters more than similarity; semantic catches concepts. gemma-forge's retrieval
docstring documents *why*: `rule_id` embeddings "collapse on superficial
similarity" → vector-only reproduces a class of false positives. Never vector-only.

## 8. Harvested patterns (from openbrain — SOURCES has paths)

Retired as a system, mined for design:
- **`open_loops`** — a first-class memory type for *unresolved threads*. Nothing
  else in the lineage has it; for a personal agent, "what did Ken and I leave
  hanging" is gold. Carry over.
- **`memory_entities` + `memory_links`** — flat entity-resolution + edge tables.
  A lighter complement to Graphiti; fixes Hermes's native entity-resolution gap
  ("Alice from engineering" = "my coworker Alice").
- **MCP adapter spec** — the interop face, already written (§4).
- **`extractors` + `embedder`** module split; **RLS** for multi-client isolation.

## 9. Open questions (resolve at build)

1. **Per-tier evaluator design.** Procedural ports the gemma-forge judge;
   factual/preference proxy-scorers to be specified (signal-forge's shadow-book
   is the template for procedural).
2. **Run location.** gyrus as its own DMZ service (`.11`) that the Pip VM calls,
   vs. co-located in the Hermes VM. Leaning own-service — the MCP face then
   comes free and other agents can reach it.
3. **Embeddings.** Gateway model (metered, consistent) vs. local Ollama
   (zero-token, another dep). Affects the pgvector dimension.
4. **Zulip backfill.** One-shot history import vs. live tail (Zulip's topic
   structure is free episodic organization — see SOURCES).
5. **RAGFlow / deep corpus.** A *separate* tier (document search), not part of
   this learning-memory stack. Its rebuild is its own project.
