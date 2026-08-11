# gyrus — tasks

Working checklist, grouped by milestone (see PLAN.md). Check off as you go;
keep this honest — it's the fast read on where the build actually is.

## Now / next
- [x] **Decide run-location** — DECIDED 2026-08-11 (ADR-0004): own DMZ service
      on `.11`; the Hermes provider becomes a thin HTTP client.
- [x] **Decide embeddings** — DECIDED 2026-08-11 (ADR-0005): gateway
      `kaiju/mxbai-embed-large`, pgvector `vector(1024)`.
- [x] Read the three sources in `docs/references/SOURCES.md` (gemma-forge memory
      modules, signal-forge consolidate.py, openbrain schema+MCP spec).
      Verified against source 2026-08-11 — deltas from the handoff docs noted in
      the session report (retrieval.py is NOT hybrid; no embedding pipeline
      exists anywhere in the lineage; eviction is threshold-retirement, not
      time-decay; signal-forge consolidates nightly, not weekly).

## M0 — the wire
- [x] Project skeleton: pyproject, package layout, config, `/data/docker/gyrus/.env`.
- [x] Mint scoped gateway key `gyrus` (into the .env, 600) — scope:
      `kaiju/mxbai-embed-large`, `vllm/qwen-35b`, `kaiju/nemotron:70b`.
- [x] Create Postgres DB `gyrus` on Supabase `.220`; pgvector 0.8.0 installed
      (ships with the image — the openbrain "gotcha" was a dimension mismatch,
      see docs/journal/gotchas/).
- [x] Provider written against the REAL Hermes ABC (verified from source, not
      the SQLite skeleton — richer contract: queue_prefetch, full messages).
      → `provider/gyrus/`, stdlib-only, thin HTTP client per ADR-0004.
- [x] `sync_turn` → raw turn to episodic store; `prefetch` → trivial recall.
      Service live on `10.0.13.11:8000`; wire verified from DMZ + LAN vantages.
- [ ] **Demo from shadesmar:** copy `provider/gyrus/` →
      `$HERMES_HOME/plugins/gyrus/`, set `memory.provider: gyrus` +
      `GYRUS_BASE_URL=http://10.0.13.11:8000`; capture a turn, see a recall
      injected. (Needs Ken — no ssh key from this host to shadesmar.)
- ~~BLOCKED~~ RESOLVED 2026-08-11: kaiju gateway lanes fixed (dmz backlog #4
  done — leg removed, routes repointed, /v1 stripped). Embeddings verified
  1024-dim through the gateway with the gyrus key. M1 is unblocked.

## M1 — episodic + retrieval
- [ ] Extraction pass (facts/decisions, not transcript) on `sync_turn`.
      Dry-run #1 done 2026-08-11 (`tools/extraction-eval/`): use the
      judge-class model (nemotron:70b beat qwen-35b decisively on domain
      facts, both 100% precision); solve the recurring-preference miss.
- [ ] **Extraction test phase (gate for M1 done):** golden set of ≥5 real
      windows incl. cron (must extract ~nothing); Ken grades the answer
      key; accept at ≥80% keep-rate, <5% noise. Model bake-off incl.
      union-of-two.
- [ ] One-time backfill: state.db (158 sessions/10.5k msgs) through the
      extraction pass; MEMORY.md/USER.md as seed facts. (Replaces the
      cancelled openbrain import — see docs/references/OPENBRAIN-AUDIT.md.)
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
