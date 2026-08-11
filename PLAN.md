# gyrus — build plan

Milestones in build order. Each is a real stopping point; the first is demoable.
Everything is testable **from shadesmar over LAN→DMZ before Pip migrates** —
that's the point of doing gyrus as Phase 3 of the Hermes integration.

## M0 — the wire (demoable)

Prove the `MemoryProvider` plumbing end-to-end, with the dumbest possible brain.
- Copy Hermes's SQLite provider skeleton; register gyrus as Pip's provider.
- `sync_turn` writes the raw turn to the episodic store; `prefetch` returns a
  trivial recall.
- **Demo:** from shadesmar, Pip captures a turn into gyrus and gets *something*
  injected before the next one. The seam works.
- Deferred: extraction, ranking, consolidation.

## M1 — real episodic + hybrid retrieval

Make recall actually useful.
- `sync_turn` runs the **extraction pass** (facts/decisions, not transcript) →
  Postgres. Port `reflector_parser.py`'s *pattern*, rewritten for Pip's turn.
- `prefetch` runs the **hybrid ranker** (keyword + semantic + graph), served from
  a background cache. Adapt gemma-forge `retrieval.py`.
- **Done when:** Pip's injected recalls are relevant to the current turn.

## M2 — the dream pass (memory stops rotting)

Port the consolidation engine.
- Port gemma-forge `dream/pass_.py` + `memory/eviction.py` (as-is).
- Offline trigger: `on_session_end` / a timer enqueues; runs out-of-band;
  writes a markdown report; idempotent via `consolidated_at` (signal-forge).
- Decay, salience grading, promotion.
- **Done when:** stale memories fade, and a recurring-but-useless memory does
  NOT outrank a rare-but-valuable one.

## M3 — procedural tier + the shadow book (PROVES THE CLAIM)

The proof tier (ADR-0002).
- Wire the **outcome-signal writer** for procedural memories: Pip reuses a
  remembered command → tool runs → pass/fail → `outcome_value`.
- Port credit assignment + causal attribution (the `tip_followed` judge) — it
  ports 1:1 once the signal writer feeds it.
- **Measure:** does Pip's tool-success-on-recall climb over sessions (the
  gemma-forge 20→90 curve, on Pip's real work)? This is the falsifiable test.

## M4 — factual + preference tiers + the entity graph

Fill in the non-ground-truth tiers, honestly.
- Factual: contradiction detection + corroboration scoring.
- Preference: proxy signals (corrected/reused/uncontradicted), never dressed up.
- Entity resolution: Graphiti + openbrain's flat `memory_entities`/`memory_links`.
- **`open_loops`**: first-class unresolved-thread memory (openbrain harvest).

## M5 — the MCP face (cross-agent)

Same store, second face (ADR-0003).
- Implement openbrain's MCP adapter spec against the gyrus store.
- The deliberate, authenticated internet-exposure design (only now does it
  leave the LAN). Claude/OpenAI/Gemini read the same brain.

## M6 — ingest breadth + production

- Zulip backfill (topic = free episodic structure) — one-shot import then tail.
- Prometheus metrics (consolidation runs, memory counts, recall latency, the
  procedural success curve).
- Resolve run-location (own DMZ service on `.11` vs. Hermes-VM co-located) and
  provision the reserved allocation (LAB.md).

## Deliberately out of scope

- **RAGFlow / deep-corpus RAG** — a separate tier and a separate project.
- **Rebuilding Hermes's capture/storage** — it already does per-turn capture;
  gyrus is the hygiene layer, not the recorder.
