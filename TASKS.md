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

## M1 — episodic + retrieval  ✅ SHIPPED 2026-08-12
- [x] Extraction pass (facts/decisions, not transcript) on `sync_turn`.
      Dry-run #1 done 2026-08-11 (`tools/extraction-eval/`): use the
      judge-class model (nemotron:70b beat qwen-35b decisively on domain
      facts, both 100% precision); solve the recurring-preference miss.
- [x] **Extraction test phase:** PASSED — 96% keep-rate, 0% noise. Union
      landed as nemotron:70b + gpt-oss:120b (complementary, not redundant).
- [x] One-time backfill: state.db, cron-filtered (47 non-cron sessions /
      2,787 msgs — the other 111 sessions were cron), windowed, idempotent.
      ~1,200 memories on the first pass; gap-fill run after.
- [ ] MEMORY.md / USER.md as seed facts (small, hand-checkable — do last).
- [x] Postgres episodic + semantic schema (0002: tier, provenance,
      vector(1024), entities, memory_retrievals seam for M3).
- [x] Hybrid ranker — GREENFIELD, not a port (gemma-forge's isn't hybrid):
      keyword(FTS) + semantic(pgvector) + entity graph, fused by RRF with an
      IDF-weighted graph leg, a cosine floor, and a multi-leg agreement bonus.
- [x] Background cache: provider-side (client thread) + service-side workers
      — no model call on Pip's turn path.
- [x] Recall relevance check on real memories: 5/5 relevant on tested
      queries, multi-leg agreement on every hit.
- [ ] Recall relevance check on LIVE Pip turns (needs the provider activated
      on shadesmar — one config line + restart).

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
