# ADR-0003: One store, two faces — Hermes MemoryProvider + MCP server

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** Ken

## Context

Two consumers want the same brain. Pip (Hermes) needs an *always-injected*
memory that recalls before every turn and captures after. Ken also wants — later
— Claude, OpenAI, and Gemini to share the same memory of him, on demand. Building
two stores would guarantee drift.

Hermes exposes a real `MemoryProvider` abstract base class (`hermes memory
setup`, pluggable — Mem0, SuperMemory, or ours): abstract `initialize` /
`prefetch` / `sync_turn`, plus optional no-op hooks (`on_session_end`,
`on_pre_compress`, `get_tool_schemas`, `handle_tool_call`), convention-based
discovery, no core edits, a SQLite skeleton to copy. Separately, MCP is the
cross-agent transport every model now speaks; openbrain already wrote an MCP
adapter spec for exactly this brain.

## Decision

**One store, two faces.**
- **MemoryProvider face** → Hermes. `sync_turn` = episodic ingest, `prefetch` =
  ranker-from-cache, `on_session_end`/`on_pre_compress` = enqueue the (offline)
  dream pass, tool hooks = expose audit/query to Pip.
- **MCP face** → Claude/OpenAI/Gemini, on demand. Reuse openbrain's adapter:
  `add_memory` / `search_memory` / `recent_memory` / `open_loops`, read/write
  tools separated, `request_id` logging.

v1 ships the MemoryProvider face only; the MCP face is designed-for but deferred
(it needs a deliberate authenticated internet exposure — not a LAN concern yet).

## Consequences

- Build once; no drift between agents.
- `prefetch` must be fast — it returns from a background-populated cache, never
  runs consolidation inline. The dream pass stays out-of-band on a timer.
- The store schema must serve both a turn-shaped provider and a tool-shaped MCP
  API; design the core store neutral to either face.
- OpenBrain survives only as the *reference* for the MCP face, not as a running
  system (ADR-0001 / harvest).
