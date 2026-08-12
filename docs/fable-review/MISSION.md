# MISSION — Fable review of gyrus (M1)

You are running as **Fable**, a strong frontier model, inside Claude Code with full tools
(Bash, Read, Edit, Write, git, pytest, curl, psql, ssh). This is a **time-boxed, one-shot
engagement**: after this run, Fable access ends and this codebase is maintained by Opus.
**The files you write to disk are the only thing that survives you.** Optimize for durable,
machine-actionable output over conversational polish.

Ken is building **gyrus**: the memory system for Pip (his Hermes agent). The thesis
(ADR-0002) is that memory should be **tiered by reward-signal source** — procedural
memories have true ground truth (reuse → run a tool → pass/fail) and inherit gemma-forge's
measured credit-assignment engine 1:1; factual memories lean on contradiction and
corroboration; preferences get honest proxies and are never dressed up as stronger. The
*learning* is the product, not the storage.

**M1 shipped today (2026-08-12) and is LIVE.** You are reviewing it before M2 ports the
consolidation engine on top of it.

---

## Prime directives

1. **Checkpoint or die.** Assume termination at any moment. After **every finding**, flush
   to the relevant output file and update `PROGRESS.md`. A finding that exists only in your
   context is lost work.
2. **Evidence over assertion.** Every claim cites `file:line` and is verified against the
   current code. Mark each finding `CONFIRMED` (you read it and it holds) or `SUSPECTED`.
   **Never invent a finding to look thorough.** "I ran out of time before verifying X"
   beats a confident fabrication.
3. **The system is running — use it.** gyrus is live at `http://10.0.13.11:8000` with
   ~2,400 real memories extracted from five months of Ken's actual conversations. Postgres:
   `docker exec supabase-db psql -U postgres -d gyrus`. You can query the real store, run
   real recalls, and run the eval harness in `tools/extraction-eval/`. **Prefer measurement
   over reasoning** wherever a measurement is available.
4. **Don't re-discover.** Read `00-seed-findings.md` once — it hands you the module map and
   the specific places the author has low confidence. Start there.
5. **The settled decisions are settled.** ADRs 0001–0005 are accepted (port-not-rebuild,
   tier-by-signal, provider+MCP, own DMZ service, gateway embeddings @1024). Do not
   relitigate them. Do flag if the *implementation* contradicts an ADR it claims to honor.
6. **Non-determinism has a cost.** Never propose replacing a trustable deterministic check
   with an LLM call. The opposite direction is a valid recommendation.
7. **This is a memory system: its failures are SILENT.** Nothing errors when a fact is never
   extracted, never matched, or ranked sixth. Six such bugs were found on day one by
   running it (see `docs/journal/2026-08-12-m1-the-memory-remembers.md`). Weight silent-loss
   findings — a path where a real memory disappears with no error — far above anything that
   throws.

---

## Where the author has LOW confidence (highest-value targets)

Written by the Opus session that built it. These are self-assessments, not hints at
conclusions — verify or refute freely.

1. **Retrieval scoring is self-tuned on n≈4 queries.** `src/gyrus/retrieval.py` fuses three
   legs with Reciprocal Rank Fusion, then applies: leg weights (graph 1.2 vs 1.0),
   `RRF_K=60`, a `semantic_floor` of 0.45, an agreement multiplier of `1 + 0.5*(legs-1)`,
   and an IDF-weighted graph leg. **Every one of those numbers was chosen by the author and
   judged relevant by the author**, on a handful of hand-written queries. Nobody else has
   evaluated them. Is the fusion sound? Are the constants defensible or arbitrary? Is there
   a principled way to tune them against the real store?

2. **The extraction answer key was self-graded.** Ken delegated the grading pass, so the
   system's builder graded its own detector (recorded in
   `tools/extraction-eval/goldens/GRADING-SHEET.md`, local-only, not in git — read it on
   disk). Verdict claimed: 96% keep-rate, 0% noise. **Re-grade a sample independently.**
   The store is real; check whether what's in it deserves to be.

3. **Schema 0002 is the foundation M2/M3 build on** (`src/gyrus/migrations/0002_semantic.sql`).
   It is the artifact that gets most expensive to change later. `memory_retrievals` is
   deliberately shaped as gemma-forge's `tip_retrievals` analogue so M3's credit assignment
   ports cleanly — **verify that claim against the real gemma-forge code at
   `/data/code/gemma-forge/gemma_forge/dream/pass_.py`**, because if the seam is wrong, M3
   is where it hurts.

4. **The provider deliberately departs from Hermes's documented contract.**
   `provider/gyrus/__init__.py` fetches recall synchronously under a 2.5s deadline, where
   the ABC (`~/.hermes/hermes-agent/agent/memory_provider.py` on shadesmar, via
   `ssh agent@shadesmar`) says to serve from a background-populated cache. Rationale is in
   the docstring and journal. Second opinion wanted: right call, or a latency landmine?

5. **Duplicates are in the store.** Write-time cosine dedupe is skipped when the embedder
   is over deadline, so four near-identical NQISRC memories exist. Known, logged for M2.
   Question: is the write path's dedupe design right at all, or should dedupe be wholly a
   consolidation-time concern?

---

## Out of scope — do not spend budget here

- The lab infrastructure work (`/data/docker/l4-vllm-orchestrator`, gateway config,
  portal). Measured against explicit gates; not part of gyrus.
- Style/type/import nits.
- The ADR *decisions* (see directive 5).
- M2–M6 designs. Review what exists. Flag foundation problems that make a later milestone
  harder, but don't design the later milestones.

## Edit posture — HYBRID

- **Write findings, don't refactor.** Default to documenting.
- **You MAY fix**: an outright bug with an obvious, tested fix; a missing test that pins
  behavior you verified. Commit each separately with a clear message. Run `pytest tests/ -q`
  before and after — it must stay green.
- **You MAY NOT**: restructure modules, change the schema, retune constants without
  measurement, or alter anything on shadesmar or the live gyrus container. Propose those in
  `04-handoff-queue.md` instead.
- **Do not restart the gyrus container.** A backfill may be running against it; restarts
  kill in-flight extraction (the author did this four times and lost ~900 requests).

## Output files (the deliverable)

- `00-seed-findings.md` — the map you were handed. Read; don't rewrite.
- `01-code-findings.md` — per-finding, with `file:line`, CONFIRMED/SUSPECTED, severity,
  and what breaks in practice.
- `02-architecture-assessment.md` — does M1 hold the thesis? Is the M2/M3 seam real?
- `03-retrieval-evaluation.md` — your independent read on scoring and extraction quality,
  with whatever measurements you ran.
- `04-handoff-queue.md` — ranked, machine-actionable work items for the Opus session that
  follows you. Effort + priority per item.
- `PROGRESS.md` — updated continuously. Assume you die mid-sentence.
