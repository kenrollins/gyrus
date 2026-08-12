# 00 — Seed findings: the map (written by the Opus session that built M1)

Read once. Don't re-derive the inventory. Everything below was true at
commit time on 2026-08-12; verify anything you intend to rely on.

## What exists

| Path | What it is | Confidence |
|---|---|---|
| `src/gyrus/migrations/0001_episodic.sql` | episodic scratch: sessions, turns (full message JSONB), FTS | solid, simple |
| `src/gyrus/migrations/0002_semantic.sql` | **the foundation**: memories (tier/provenance/vector(1024)), memory_entities, memory_retrievals (M3 seam) | **review target #3** |
| `src/gyrus/gateway.py` | the only door to inference; chat + embeddings, tolerant JSON salvage | salvage logic is load-bearing |
| `src/gyrus/extraction.py` | the v1 prompt, validation, union pass, persist+dedupe | **review target #2** |
| `src/gyrus/retrieval.py` | hybrid ranker, RRF fusion, three legs | **review target #1** |
| `src/gyrus/worker.py` | background extraction, sweepers (turn + embedding repair) | |
| `src/gyrus/api.py` | HTTP face; the seam the provider and future MCP share | |
| `provider/gyrus/__init__.py` | Hermes MemoryProvider, stdlib-only thin client | **review target #4** |
| `tools/backfill_state_db.py` | state.db → gyrus, cron-filtered, windowed, idempotent | |
| `tools/extraction-eval/` | the golden-set harness + all measurements | the evidence base |
| `tests/test_m1.py` | 16 regression tests, each a real bug from day one | |

## What is MEASURED (trust, but re-check the method)

- Extraction model choice: `kaiju/nemotron:70b` beat qwen-35b, the 120B, and Lightning on
  a real conference window. Full matrix in `tools/extraction-eval/README.md`. The 120B
  *lost* domain facts the 70B caught — scale was not the lever, prompt design was.
- Union partner `kaiju/gpt-oss:120b` chosen because it is **complementary**, not better:
  the 70B returns domain insights, gpt-oss returns the reference layer (addresses,
  versions, open loops). Measured on the same window.
- Recall latency ~120 ms warm from the agent host; ~80 ms for the two Postgres legs.
- Live loop verified: Hermes sessions `20260812_190658` and `20260812_205344` each
  retrieved 5 memories and were captured back into the episodic store.

## What is ASSUMED (unverified — good hunting)

- That RRF is the right fusion for these three legs, and that the tuning constants
  generalize past the queries they were tuned on.
- That the tier taxonomy survives contact with real data. Current store skews
  `assistant_suggested` (872 of ~1900 at last count) — **is that tier/provenance
  assignment honest, or is the extractor laundering the assistant's own suggestions into
  memories about Ken?** This is the one that most worries the author: ADR-0002's stated
  failure mode is exactly "confidently-wrong preference memories".
- That `open_loop` as a tier (rather than a status flag) is right.
- That the 45-day Hermes prune makes the episodic tier disposable — gyrus keeps turns
  forever right now, with no retention policy of its own.
- That extraction is idempotent enough that re-running the backfill is safe. It dedupes by
  hash then cosine; nobody has tested the third run.

## Known-broken / deliberately deferred

- ~466 turns have `extracted_at IS NULL` (backfill interrupted by the author's own
  container restarts). The sweeper skips backfill-tagged turns by design, so these need a
  backfill re-run, not a sweep. Not a code bug; verify the reasoning.
- Four near-identical NQISRC memories (dedupe skipped during an embedder stall).
- `get_tool_schemas()` returns `[]` — gyrus has no write tools, so Pip cannot deliberately
  remember anything. Five Hermes sub-profiles still have SOUL.md prose instructing them to
  write to the retired OpenBrain. Real gap, M5 scope.
- No Neo4j/Graphiti (M2+). The "graph" leg is the flat entity table, not a graph.

## Context worth reading (in this order, ~20 min)

1. `BRIEF.md` — the claim and how to falsify it
2. `docs/adr/0002-tier-by-signal-source.md` — the thesis
3. `docs/journal/2026-08-12-m1-the-memory-remembers.md` — the six silent failures, and how
   the `legs` diagnostic found them
4. `tools/extraction-eval/README.md` — every measurement behind the model choices
5. `docs/references/OPENBRAIN-AUDIT.md` — why the predecessor's corpus was NOT migrated
   (relevant: it is a worked example of this project's own quality bar)
