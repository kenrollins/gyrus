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
- [x] **Demo from shadesmar:** DONE 2026-08-12. Provider installed at
      `~/.hermes/plugins/gyrus/`, `memory.provider: gyrus`, GYRUS_BASE_URL in
      `.env`, gateway restarted. `hermes memory` shows "gyrus ← active".
      Live session 20260812_190658 retrieved 5 memories AND was captured
      back into the episodic store. The wire is closed both directions.
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
- [x] Recall relevance check on LIVE Pip turns — verified end to end.

## M1.5 — harden M1 (Fable review) — DO FIRST, precedes M2
- [ ] **F2:** drop the ivfflat index (28% recall@10 at 2.5k rows); flat scan
      until >100k rows. Re-run all semantic-leg measurements after.
- [ ] Finish the interrupted backfill (465 turns `extracted_at IS NULL`).
- [ ] Stage the F4 reclassification: `assistant_suggested` domain facts with no
      personal anchor → `knowledge` tier (needs M4 schema; flag now, sweep after).
- Full findings: `docs/fable-review/04-handoff-queue.md`.

## M2 — dream pass (shared framework, per-tier evaluators)
- [ ] Port `dream/pass_.py` + `memory/eviction.py` as a framework; plug in the
      per-tier evaluator (ADR-0002/0006), not one global rule.
- [ ] Wire the evaluators that don't need M3's outcome signal: factual
      corroboration + **knowledge recency/retrieval-demand decay**.
- [ ] **Near-duplicate merge** (F5): consolidation merges near-dups + folds
      corroboration counts (don't trust the write path; root cause was F2).
- [ ] Neo4j + Graphiti reflective tier wired.
- [ ] Offline trigger (`on_session_end` / timer), out-of-band, idempotent
      `consolidated_at` + markdown report.
- [ ] Decay test: recurring-useless does NOT outrank rare-valuable; stale
      never-retrieved knowledge fades.

## M3 — procedural tier (PROVES THE CLAIM)
- [ ] Outcome-signal writer: tool pass/fail → `outcome_value` (procedural).
- [ ] Port credit assignment + causal-attribution (`tip_followed`) judge.
      (Seam Fable-verified: GROUP BY memory_id, scope on followed_computed_at.)
- [ ] Instrument tool-success-on-recall; watch the curve over sessions.

## M4 — the knowledge tier (ADR-0006)
- [ ] Schema: `knowledge` tier + source_type/source_ref/topic; source-authority
      × recency × retrieval-demand evaluator.
- [ ] Retrieval integration: down-weighted vs personal tiers; excluded from the
      M3 metric.
- [ ] Extraction gate: "teaching me about Ken" (personal) vs "record the world"
      (knowledge).
- [ ] **`/v1/insights`**: browse gleaned insights by source/topic/recency.

## M5 — source ingestion adapters (ADR-0006)
- [ ] Email: reconnect `pip_signal_memory_bridge` output → knowledge tier
      (closes the dropped-insight leak from the OpenBrain retirement).
- [ ] Conference/notes: retag the existing harvest flow → knowledge tier.
- [ ] Podcast: fetch → transcribe (Whisper/kaiju) → extract.
- [ ] Web: later.

## M6 — factual + preference + graph
- [ ] Factual: contradiction detection + corroboration scoring.
- [ ] Preference: proxy signals (corrected/reused/uncontradicted).
- [ ] Entity resolution (Graphiti + flat `memory_entities`/`memory_links`).
- [ ] `open_loops` (unresolved-thread memory).

## M7 — MCP face
- [ ] openbrain MCP adapter spec against the gyrus store; read/write split;
      request_id logging; add/search/recent/open_loops + insights.
- [ ] **Auth (Fable F3):** store is unauthenticated on DMZ today — scoped token
      before the MCP face leaves the LAN.

## M8 — ingest breadth + production
- [ ] Zulip backfill from the Zulip server (pre-Hermes history, no 45-day prune).
- [ ] Prometheus metrics (consolidation, counts by tier, recall latency, success
      curve, knowledge freshness).
- [ ] Provision the reserved `.11` allocation (LAB.md); operator DNS/Authentik
      only if a public face is wanted.

## Guardrails to hold the whole way
- [ ] Never store transcripts as memory (extract first).
- [ ] Never vector-only retrieval (hybrid).
- [ ] Never score a preference as if it had procedural ground truth.
- [ ] Consolidation offline only, never mid-turn.
- [ ] Inference only via the gateway with the scoped key.
