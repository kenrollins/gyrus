# gyrus — build plan

Milestones in build order. Each is a real stopping point; the first is demoable.
Everything is testable **from shadesmar over LAN→DMZ before Pip migrates** —
that's the point of doing gyrus as Phase 3 of the Hermes integration.

> **Roadmap expanded 2026-08-13 (ADR-0006).** gyrus now carries two memory
> families: *personal* memory about Ken (procedural/factual/preference —
> outcome & corroboration signals, the falsifiable thesis) and *knowledge*
> distilled from curated high-signal sources (conference/email/podcast/web —
> source-authority/recency/demand signals). Both live in one store; the back
> half of the plan gains the knowledge tier, its ingestion adapters, and a
> visibility surface. The two families are parallel tracks after M2: M3 proves
> the personal thesis; M4–M5 build out knowledge. Sequence them by Ken's
> priority, not strictly in number order.

## M0 — the wire (demoable) ✅ SHIPPED 2026-08-11
Prove the `MemoryProvider` plumbing end-to-end with the dumbest possible brain.
Service on `.11`; `sync_turn` → episodic store; `prefetch` → trivial recall.

## M1 — real episodic + hybrid retrieval ✅ SHIPPED 2026-08-12
Extraction pass (facts, not transcript) + hybrid ranker (keyword+semantic+graph,
RRF-fused) served under a deadline. Backfilled 5 months of real conversation;
live loop verified in real Hermes sessions. Independent Fable review followed
(`docs/fable-review/`): held-out recall hit@5=92%, M3 seam validated, two HIGH
findings (F2 ANN index, F4 knowledge-vs-memory) → M1.5 and ADR-0006.

## M1.5 — harden M1 (from the Fable review) — DO FIRST
Small, foundational, cheap now / expensive later. Precedes M2.
- **F2:** drop the ivfflat index (28% recall@10 at this scale); flat scan until
  >100k rows. Fixes the semantic leg AND write-time dedupe (F5) in one change.
- **Finish the backfill** (465 turns unextracted after restarts); re-run clean.
- **F4 reclassification pass:** move the ~710 mislabeled `assistant_suggested`
  domain facts into the new `knowledge` tier (needs M4 schema — or stage a
  `source`/`reclassify_pending` flag now and sweep after).
- Re-run all semantic-leg measurements post-F2.

## M2 — the dream pass (memory stops rotting)
The consolidation engine, as a **shared framework with per-tier evaluators**
(ADR-0002/0006) — not one global rule.
- Port gemma-forge `dream/pass_.py` + `memory/eviction.py`; offline trigger
  (`on_session_end`/timer), out-of-band, idempotent via `consolidated_at`,
  markdown report.
- Wire the evaluators that DON'T need M3's outcome signal yet: factual
  corroboration, and **knowledge recency + retrieval-demand decay**.
- **Near-duplicate merge** (F5): consolidation merges near-dups and folds their
  corroboration counts — don't rely on the write path.
- **Done when:** stale memories fade, a recurring-but-useless memory does NOT
  outrank a rare-but-valuable one, and never-retrieved knowledge decays.

## M3 — procedural tier + the shadow book (PROVES THE CLAIM)
The proof tier (ADR-0002); the personal-memory track's payoff.
- Outcome-signal writer: Pip reuses a remembered command → tool runs →
  pass/fail → `outcome_value` (the `memory_retrievals` seam is already shaped
  for this — Fable-verified against real `pass_.py`; credit SQL groups by
  `memory_id`, scopes on `followed_computed_at IS NULL`).
- Port credit assignment + causal attribution (`tip_followed` judge).
- **Measure:** does Pip's tool-success-on-recall climb over sessions (the
  gemma-forge 20→90 curve, on Pip's real work)? The falsifiable test.

## M4 — the knowledge tier (ADR-0006)
The knowledge-memory track's foundation.
- Schema: `knowledge` tier + `source_type` / `source_ref` / `topic`; the
  source-authority × recency × retrieval-demand evaluator.
- Retrieval integration: participates in hybrid recall, **down-weighted vs.
  personal tiers**; never enters the M3 metric.
- Extraction gate: split "Ken teaching me about himself" (personal tiers) from
  "Ken directing me to record the world" (knowledge tier).
- **`/v1/insights` visibility surface:** browse what's being gleaned, by source
  and topic and recency. The "let me SEE the insights" requirement.
- **Done when:** the conference corpus is queryable AND browsable as knowledge,
  and it never dilutes a personal-memory recall.

## M5 — source ingestion adapters (ADR-0006)
Thin producers, one store. Build once.
- **Email:** reconnect `pip_signal_memory_bridge` output → gyrus knowledge tier
  (closes the leak the OpenBrain retirement opened — insights currently dropped).
- **Conference/notes:** retag the existing harvest flow into the knowledge tier.
- **Podcast:** new — fetch feed → transcribe (Whisper on kaiju) → extract; or
  adopt the dmz Phase-4 `podcast-ingestor` if/when it lands.
- **Web:** later (website_scraper analogue).
- **Done when:** a new high-signal item from each live source appears in
  `/v1/insights` within its cadence, attributed to its source.

## M6 — factual + preference tiers + the entity graph
Refine the non-ground-truth personal tiers, honestly.
- Factual: contradiction detection + corroboration scoring.
- Preference: proxy signals (corrected/reused/uncontradicted), never dressed up.
- Entity resolution: Graphiti + openbrain's flat `memory_entities`/`memory_links`.
- **`open_loops`**: first-class unresolved-thread memory (openbrain harvest).

## M7 — the MCP face (cross-agent)
Same store, second face (ADR-0003). Now `/v1/insights` + memory tools have a
real cross-agent surface.
- openbrain's MCP adapter spec against the gyrus store; read/write split;
  `request_id` logging.
- **Auth (Fable F3):** the store is unauthenticated on the DMZ today — fine for
  LAN v1, a hard blocker here. The deliberate, authenticated internet-exposure
  design; only now does it leave the LAN.

## M8 — ingest breadth + production
- Zulip backfill from the Zulip server directly (topic = free episodic
  structure) — pre-Hermes history, unaffected by the 45-day prune.
- Prometheus metrics (consolidation runs, memory counts by tier, recall
  latency, the procedural success curve, knowledge freshness).
- Provision the reserved `.11` allocation (LAB.md); operator DNS/Authentik only
  if a public face is wanted.

## Deliberately out of scope
- **RAGFlow / deep-corpus RAG** — the RAW-DOCUMENT search tier. gyrus holds the
  *distilled insights* from sources (M4/M5); RAGFlow would hold the documents
  themselves for deep retrieval. Separate project; the line is sharper post-0006.
- **Rebuilding Hermes's capture/storage** — it already does per-turn capture;
  gyrus is the hygiene + consolidation layer, not the recorder.
