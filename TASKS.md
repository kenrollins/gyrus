# gyrus — tasks

Working checklist, grouped by milestone (see PLAN.md). Check off as you go;
keep this honest — it's the fast read on where the build actually is.

## Now / next
- [ ] **Decide run-location** (own DMZ service on `.11` vs. Hermes-VM co-located)
      — unblocks the compose/network shape. Leaning own-service (MCP face free).
- [ ] **Decide embeddings** (gateway model vs. local Ollama) — sets the pgvector
      dimension; do this before schema.
- [ ] Read the three sources in `docs/references/SOURCES.md` (gemma-forge memory
      modules, signal-forge consolidate.py, openbrain schema+MCP spec).

## M0 — the wire
- [ ] Project skeleton: pyproject, package layout, config, `/data/docker/gyrus/.env`.
- [ ] Mint scoped gateway key `gyrus` (into the .env, 600).
- [ ] Create Postgres DB `gyrus` on Supabase `.220` (client, not a rival); verify
      pgvector builds (the openbrain gotcha).
- [ ] Copy Hermes's SQLite `MemoryProvider` skeleton; register gyrus.
- [ ] `sync_turn` → raw turn to episodic store; `prefetch` → trivial recall.
- [ ] **Demo from shadesmar:** capture a turn, get a recall injected.

## M1 — episodic + retrieval
- [ ] Extraction pass (facts/decisions, not transcript) on `sync_turn`.
- [ ] Postgres episodic + semantic schema (+ fast-read projection).
- [ ] Port + adapt `retrieval.py` hybrid ranker (rule_id → Pip tokens).
- [ ] Background cache so `prefetch` returns fast.
- [ ] Recall relevance check on real Pip turns.

## M2 — dream pass
- [ ] Port `dream/pass_.py` + `memory/eviction.py`.
- [ ] Neo4j + Graphiti reflective tier wired.
- [ ] Offline trigger (`on_session_end` / timer), out-of-band runner.
- [ ] Idempotent `consolidated_at` + markdown report.
- [ ] Salience/decay test: recurring-useless does NOT outrank rare-valuable.

## M3 — procedural tier (the proof)
- [ ] Outcome-signal writer: tool pass/fail → `outcome_value` (procedural).
- [ ] Port credit assignment + causal-attribution (`tip_followed`) judge.
- [ ] Instrument tool-success-on-recall; watch the curve over sessions.

## M4 — factual + preference + graph
- [ ] Factual: contradiction detection + corroboration scoring.
- [ ] Preference: proxy signals (corrected/reused/uncontradicted).
- [ ] Entity resolution (Graphiti + flat `memory_entities`/`memory_links`).
- [ ] `open_loops` (unresolved-thread memory).

## M5 — MCP face
- [ ] Implement openbrain MCP adapter spec against the gyrus store.
- [ ] add/search/recent/open_loops tools; read-write split; request_id logging.
- [ ] Authenticated internet exposure design (first time it leaves the LAN).

## M6 — ingest + production
- [ ] Zulip backfill (one-shot import) + live tail.
- [ ] Prometheus metrics (consolidation, counts, recall latency, success curve).
- [ ] Provision the reserved `.11` allocation (LAB.md); operator DNS/Authentik
      only if a public face is wanted.

## Guardrails to hold the whole way
- [ ] Never store transcripts as memory (extract first).
- [ ] Never vector-only retrieval (hybrid).
- [ ] Never score a preference as if it had procedural ground truth.
- [ ] Consolidation offline only, never mid-turn.
- [ ] Inference only via the gateway with the scoped key.
