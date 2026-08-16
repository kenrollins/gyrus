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

## M1.5 — harden M1 (Fable review) ✅ (F2 done; F1 backfill gap closed)
- [x] **F2:** drop the ivfflat index (28% recall@10 at 2.5k rows); flat scan
      until >100k rows. Re-run all semantic-leg measurements after.
- [x] Finish the interrupted backfill (465 turns `extracted_at IS NULL`).
      Drained 2026-08-15 via `tools/backfill_pending.py`; `pending` 465 → 0,
      +385 memories. The stall had three causes, all fixed — see
      journal 019. Note the fixes matter more than the drain: an unreachable
      gateway used to STAMP turns extracted with zero facts, so the backlog
      could have silently erased itself instead.
- [x] F4 reclassification — done in two passes: the 2026-08-13 heuristic sweep
      (709 moved) and the 2026-08-15 full LLM pass over every live factual row
      (`tools/store-audit/retier_classify.py`: 1,031 world-labeled rows →
      knowledge, `source_type='conversation'`; conservative on ambiguous;
      12/16 agreement with the hand-graded sample, all disagreements
      in the stay-put direction). journal-022.
- [x] **Prompt-lineage numbers re-verified 2026-08-16** under `bench_lanes.py`
      (v1.2 on lab/extract, 6 goldens): non-cron keep-rate ~93%, 0 structural
      noise — the old claim roughly survives; facts/window ~6.8. NEW finding:
      ~20% of non-cron facts misfile world knowledge as `factual` — the
      wrong-tier defect is live prompt behavior, so the re-tier sweep must be
      periodic until the prompt learns the knowledge boundary (fold into the
      cron-suppression prompt pass below — one golden-set validation covers
      both). Historical v0/v0.1 figures stay labeled narrative-only.
- [x] **The fallback lane times out** (ADR-0010 addendum) — fixed 2026-08-15:
      `chat_json` now gives the fallback attempt its own ceiling
      (`extract_fallback_timeout`, 900s) instead of the 300s default that
      killed it on 4 of 6 golden windows. Kept `vllm/nemotron-120b` rather
      than repointing: the fallback must sit on non-kaiju silicon, and the
      only fast non-kaiju lane drops the JSON contract (ADR-0010).
- [ ] **Near-duplicates: measured 2026-08-15 (full-store exact scan) — the 15%
      figure does not replicate.** Nearest-earlier-neighbour over all 12,886
      live rows: **187 pairs ≥0.93 (~1.5% of the store is an undeduped later
      twin; ~3% of rows touched)**. Replicating the 400-sample method gives
      2.5%, not 15% — treat the old number as an instrument artifact (its
      ad-hoc SQL is unrecoverable). Mechanism split: **95% of pairs predate
      migration 0003** (the blind-ivfflat dedupe era, already fixed); the
      `if pgvec is not None` skip (#9) is REAL and has a confirmed footprint
      (one call at 2026-08-15 03:01:52, turn 823, inserted 3 facts undeduped
      during an embed failure) but accounts for only ~10 pairs. Zero
      same-source_key pairs — the 0006 independence rule is holding.
      Remaining work — (a) and (b) CLOSED 2026-08-15 (journal-022):
      (a) ✅ `persist()` now raises `GatewayError` on a vectorless batch (Ken's
      ruling; write path only — retrieval's no-vector tolerance intact;
      regression test in test_m1.py; `/v1/extract-window` translates to 503);
      (b) ✅ one-time 0.93 merge sweep ran via the dream pass — 256 merges, more
      than the 187 measured pairs because the same-day re-tier converted
      cross-tier duplicates into foldable same-tier pairs; resident backstop
      stays 0.97. (c) ANSWERED 2026-08-16 (journal-023): the band measured
      952 pairs post-cleanup; a graded 30-pair sample split ~80% same-claim
      rewordings / ~20% genuinely DISTINCT facts differing by one critical
      token (ADR-0024 vs -0018, `pip install .` vs `.[test]`,
      foam-note-link vs foam-placeholder-link). So the write threshold STAYS
      at 0.93 — lowering it would destroy ~190 distinct technical facts, the
      exact pattern-separation job in this project's name. NEW WORK instead:
      a band discriminator in the dream pass — for 0.90–0.93 nearest pairs,
      adjudicate same-claim vs distinct before folding (deterministic first:
      differing digit/identifier tokens → distinct; lab/flash for the
      remainder). Residual ≥0.93 chains converge with a second sweep pass
      (ran one: 23 folded; store 10,943).
- [x] **Cron suppression FIXED 2026-08-16** (journal-024), two layers:
      (1) deterministic — `/v1/extract-window` now 422s on any cron-platform
      turn (the worker and backfill already filtered; this was the unlocked
      door); (2) prompt v1.3 — the working tell is that automated output
      usually SAYS it is automated (cron mentions, skill-dump user messages);
      both cron goldens now return [] (were 6 and 4 facts). Golden-set
      validated; the same pass fixed the knowledge/factual boundary
      (wrong-tier ~20% -> ~0-3% on non-cron windows) and added ADR-0011's
      `expires` (model ignores the field, so `_clean` infers it
      deterministically on open_loop/preference).
- Full findings: `docs/fable-review/04-handoff-queue.md`.

## M2 — dream pass ✅ SHIPPED 2026-08-13 (framework validated; committed first run, 78 merges)
- [x] Port `dream/pass_.py` + `memory/eviction.py` as a framework; plug in the
      per-tier evaluator (ADR-0002/0006), not one global rule.
- [x] Wire the evaluators that don't need M3's outcome signal: factual
      corroboration + **knowledge recency/retrieval-demand decay**.
- [x] **Near-duplicate merge** (F5): consolidation merges near-dups + folds
      corroboration counts (don't trust the write path; root cause was F2).
- [x] Reflective tier SHIPPED 2026-08-16 (ADR-0013, journal-030) — as a
      PROJECTION, not a second store: nightly graph sync (GMemory/GEntity,
      MENTIONS, SUPERSEDED_BY provenance edges from reconciler verdicts,
      bi-temporal with retired history) + in-graph co-occurrence enrichment
      written back to Postgres `entity_relations` for the hot retrieval leg
      (one-hop expansion at half weight — recall never pays a bolt trip).
      First projection: 13,249 nodes, 28,309 mentions, 908 supersedes
      chains (3 hops deep), 4,708 relation rows ("nersc"→qcan/hamlib/
      klymko — recalls now reach memories that never name the query).
      Graphiti deliberately NOT adopted: gemma-forge declared it and never
      imported it; direct driver + our own projection (evidence in the ADR).
- [x] Offline trigger — closed 2026-08-16: `worker._dream_sweeper` runs a
      committed consolidation when the store's `max(consolidated_at)` ages
      past `consolidate_interval_hours` (24h default; restart-proof because
      cadence reads from the store, not process uptime). Until then every
      dream pass had been a human remembering — the audit's zero-shaped
      failure in scheduling form.
- [x] Decay test — demonstrated on real data: stale never-retrieved knowledge
      fades (6,038 event-time decays on 2026-08-16, May-2024 docs at full
      fade — ADR-0011); recurring-useless does not outrank rare-valuable
      (journal-018's utility ranking; source_key killed the repetition-as-
      corroboration path that would have broken this).
- [x] **Band discriminator wired into the dream pass** — subsumed by the M6
      reconciler (journal-028): 0.90–0.97 pairs adjudicated nightly with the
      double-agreement gate, capped at `reconcile_max_pairs`/run. One
      semantics change from the standalone tool: token-conflict pairs go to
      the judge (they may be contradictions), only one-sided enumerations
      stay deterministically distinct. First pass folded 44.

## M3 — procedural tier (PROVES THE CLAIM) — MECHANISM SHIPPED 2026-08-13; curve needs usage
- [x] Outcome-signal writer (`outcomes.py`): parses tool pass/fail + embedding tip_followed → `outcome_value`. Proven on real turn 1835.
- [x] Credit assignment in the dream pass (GROUP BY memory_id, min-sample guard like gemma-forge's follow_sample_size). Confidence moved 0.97→0.26 on a real failing turn, then guard held it until enough evidence.
- [x] LLM tip_followed judge — shipped 2026-08-16 (journal-026): runs only on
      embedding-flagged candidates; confirmation raises outcome confidence
      0.8→0.95, refutation corrects embedding false-positives to not-followed,
      judge-down degrades to the embedding verdict. Notably it refused to
      blame a workflow memory for a script-existence probe — the follow-gate
      protecting against unfair credit, observed live.
- [~] THE CURVE — **dynamics VALIDATED 2026-08-16** via the agent-driven
      harness (tools/m3-harness/, journal-026): 8 rounds of real reuse loops
      against the Pip VM. The store's MOST confident procedural memory
      (2114, conf 1.00, "run pip_openbrain_autopromote_candidates.py") was
      falsified by genuine probe failures → credit −0.285 on 3 samples →
      confidence 1.00→0.215 in the committed consolidation → recall
      re-ranked away from demoted memories on 3 of 4 dead-advice tasks.
      Caveat recorded: a near-verbatim query keeps a demoted memory top
      (RRF keyword dominance beats a 0.715× confidence multiplier);
      demotion→eviction closes that over time. The LONG-RUN curve
      (statistically meaningful climb) still needs organic usage volume —
      that part stays open by design.
- [x] Outcome scoring self-runs (worker sweeper); the loop is live.

## M4 — the knowledge tier (ADR-0006) ✅ SHIPPED 2026-08-13 (gyrus-side)
- [x] Schema: `knowledge` tier + source_type/source_ref/topic (migration 0004);
      recency × retrieval-demand evaluator (recency now EVENT-time, ADR-0011).
- [x] Retrieval integration: 0.6 down-weight vs personal tiers; excluded from
      the M3 metric (outcomes score procedural recalls only).
- [x] Extraction gate: personal-vs-knowledge in the prompt; boundary sharpened
      in v1.3 (wrong-tier ~20%→~0-3%, journal-024).
- [x] **`/v1/insights`** live; browses log browse_count as demand (ADR-0008).

## M5 — source ingestion (superseded by ADR-0007/0009: thalamus feeds gyrus)
- [x] github lane — shipped 2026-08-14 (thalamus adapter → trusted ingest);
      re-scoped 2026-08-16 upstream (archive/vendored exclusions + purge).
      Daily schedule live; edited docs re-cross with commit-date event time.
- [x] Email lane — shipped 2026-08-15 (ADR-0009 edge-collector push; 311
      newsletters → knowledge; published_at verified faithful).
- [x] arXiv lane — live, front-gated (ADR-0008 relevance floor). The 0.55
      floor itself is still unvalidated — see backlog below.
- [ ] **The claude lane** (Ken 2026-08-16: "could be the biggest win of this
      project") — Claude-instance insights (~/.claude/projects/*/memory/*.md
      + /data/code/*/CLAUDE.md, all hosts) as a thalamus source.
      GYRUS SIDE ✅ DEPLOYED (commit 61345ff): "claude" trusted,
      source_key=claude:<project>, ingest sweeper auto-pulls — zero manual
      steps once items flow. THALAMUS SIDE ⏳ handed off: design in
      docs/THALAMUS-CLAUDE-LANE-2026-08-16.md, green-light messaged to the
      thalamus session 2026-08-16. **If that session went stale, paste the
      doc path into any new thalamus session — it is self-contained.**
      Remaining gyrus checkbox: when items flow, verify end to end (facts
      land as knowledge/claude with mtime event_at, cross-project
      corroboration fires, provenance is NOT ken_said).
- [ ] Podcast: thalamus fetch → transcribe (Whisper/kaiju) → extract.
      Recon `pip_episode_capture.py` first (build-status note).
- [ ] Web: later.

## M6 — factual + preference + graph (reconciler shipped 2026-08-16, journal-028)
- [x] Factual contradiction detection — `reconcile.py`, in the nightly dream
      pass: 0.90–0.97 nearest pairs judged same/distinct/contradicts (double
      agreement, order-swapped); contradictions supersede newer-event-wins
      (ADR-0011 gives honest event time; bi-temporal so recoverable). First
      committed pass: 3 contradictions (incl. "IS 5527 commits behind"
      superseded by "WAS ... before the rebase" — tense as truth).
      Corroboration scoring was already live (write path + _utility).
- [x] Preference proxies — "reused" = recall demand (live in _utility);
      "corrected/uncontradicted" = the same contradiction engine applied to
      the preference tier (newer preference supersedes the one it corrects).
- [ ] Entity resolution (Graphiti + flat `memory_entities`/`memory_links`) —
      moves with the Neo4j reflective tier (M2 leftover), one build.
- [x] `open_loops` task-closure lifecycle — `reconcile.resolve_loops`:
      loops >2 days old get their top-4 later memories judged for
      resolution (conservative: doubt = stay open; evidence id must be one
      of the candidates); resolved loops retire with superseded_by pointing
      AT the resolving memory. First pass: 32 of 100 closed; the 466-loop
      backlog drains at ≤100/night on the dream cadence. `expires`
      (ADR-0011) already bounds deadline-carrying loops at write time.

## Audit backlog (small, measured, from journals 020–026)
- [x] arXiv "Ken is tracking X" fabricated-interest sweep — 16 retired
      2026-08-16 (firehose arrival is not intent; provenance-inflation class).
- [ ] **Mid-Sep re-grade** against baseline-2 (seed 0.43,
      `tools/store-audit/GRADING-BASELINE-2.md`) — the honest progress
      metric; keep-rate delta per stratum, never memory counts.
- [ ] Firehose relevance floor (0.55) — never validated (audit brief
      "never tested, and load-bearing" list; the last survivor from it).
- [ ] RRF keyword-dominance watch: a demoted memory (conf 0.215) still tops
      near-verbatim queries (journal-026 caveat). No fix yet, by choice —
      eviction closes it slowly; revisit only if organic usage shows recall
      serving known-bad advice.
- [ ] Periodic re-tier spot-check (v1.3 cut live misfiling to ~0-3%; a
      quarterly 20-row sample of new factual rows keeps it honest).
- [ ] Fold the 27 "unsure" band pairs — or leave them; unsure-means-keep is
      the designed behavior. Revisit alongside the discriminator wiring.

## M7 — MCP face ✅ SHIPPED 2026-08-16 (journal-027)
- [x] MCP face live at `/mcp` on the service (`src/gyrus/mcp_face.py`),
      per the openbrain adapter spec fetched from kaiju: search_memory /
      recent_memory / open_loops / insights / add_memory; read/write split
      (the one write goes through extraction.persist — embedded, deduped,
      backpressured, provenance assistant_suggested); request_id logging;
      server-side limit caps. MCP searches log retrievals and insights
      browses bump browse_count — cross-agent demand feeds the same
      ADR-0008 signal Pip feeds. SDK note: FastMCP is now MCPServer; the
      SDK's DNS-rebinding Host allow-list broke server-to-server calls and
      is deliberately off (the bearer is the boundary — comment in code).
- [x] **Auth (Fable F3) closed:** bearer token on everything except /health
      (constant-time compare, middleware). Deployed zero-gap: VM provider +
      env updated FIRST (old service ignored the header), hermes restarted,
      THEN enforcement switched on — no capture window lost. Verified: 401
      bare, 200 with token, zero provider 401s after cutover.
- [ ] Public exposure (Caddy route + Authentik, per LAB.md) — only if/when
      Ken wants the face reachable off-LAN; the token is necessary but not
      sufficient for that step.

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
