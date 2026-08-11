---
id: journal-001-handoff-survives-contact
type: journal
title: "The handoff survives contact with the source — mostly"
date: 2026-08-11
visibility: public
tags: [verification, gemma-forge, signal-forge, openbrain, provenance]
related:
  - adr/0001-port-not-rebuild
  - adr/0002-tier-by-signal-source
  - references/SOURCES
one_line: "Read-before-port verification of all three source systems: the crown jewel is real and portable, but 'hybrid retrieval', 'decay', and 'weekly consolidation' turned out to be plans the docs remembered as facts."
principle: "A design handoff is a set of claims about code. Verify every load-bearing claim against source before building on it — the doc author's memory merges what shipped with what was intended."
---

gyrus starts life as a complete design handoff: BRIEF, ARCHITECTURE, five ADRs,
a module-lift map naming exact files in three prior systems. Day one's job was
not to build — it was to check whether the handoff's claims survive contact
with the source they cite. House discipline: read the modules before porting
them.

## What held

The claim the whole project stands on is intact. gemma-forge's dream pass
(`dream/pass_.py`, 927 lines) is genuinely de-STIG'd: `skill` is a parameter
threaded through every function, and the credit math reads `outcome_value`,
`tip_followed_llm`, `tip_followed_emb` from a `tip_retrievals` table. No
scanner calls anywhere in the file. The signal-production / signal-consumption
seam (`OutcomeSignal` + `EvaluatorMetadata` in `harness/interfaces.py`) is as
clean as advertised — graded salience (1.0 first-try / 0.8 / 0.5 / negative
for harmful) lives entirely in per-skill evaluators, outside the memory
subsystem. Swap the evaluator, keep the machinery: the port thesis (ADR-0002)
is real.

signal-forge's precedent port also held: deterministic shadow-book outcomes
(benchmark-relative forward return, ±20% → full signal) feed tip confidence at
learning rate 0.2, with follow-aware modifiers {followed 1.0, partial 0.7,
overrode 0.5} — DEF-27 transplanted to a second domain, working.

## What the docs remembered wrong

Four claims did not survive, and each changes build work:

1. **"Hybrid ranker" is aspirational.** `memory/retrieval.py` has no BM25, no
   vector search, no graph — it's lexical prefix similarity over STIG rule
   IDs, a category bonus, and a follow-aware historical hit rate, fused in
   Python. The celebrated "vector-only fails" docstring argues specifically
   about *rule-ID embeddings collapsing on shared tokens* — an argument that
   does not transfer to natural-language memories. Our hybrid retrieval is
   greenfield with a ported scoring skeleton, not an adaptation.

2. **Nothing in the lineage ever shipped an embedding pipeline.** gemma-forge
   defines `vector(768)` columns that no code writes or reads (the "Phase G"
   embedder never landed); its only embedding use is an in-process MiniLM
   producing a scalar cosine for the follow-judge. signal-forge deliberately
   deferred embeddings. openbrain actually ran them (mxbai-embed-large,
   1024-dim via a LiteLLM alias) — the one live precedent, in the system the
   handoff calls "thin". The embedding decision was therefore unconstrained:
   no inherited dimension exists.

3. **"Decay" is not decay.** `memory/eviction.py` implements
   evidence-thresholded soft retirement — lifetime average utility below
   threshold after ≥N retrievals — with no time component, no half-life, no
   recency weighting. If gyrus wants Ebbinghaus-style fading, that is new
   code, not a port.

4. **signal-forge consolidates nightly, not weekly.** The plan said weekly
   timer + manual-grade trigger; the shipped system runs the pass every night
   inside its nightdesk job, idempotent via a `consolidated_at` stamp, so
   most nights are a no-op. That's a better pattern than the documented one —
   cheap idempotent passes at a short cadence beat a long timer plus a
   trigger path — and gyrus will copy the shipped version, not the plan.

Two smaller finds with build consequences: the dream-pass judge is still
hardwired to a pre-gateway vLLM URL (the one component that never got
migrated when the rest of gemma-forge moved to the metered gateway), and the
judge compares tips against *untruncated action text reconstructed from run
logs* because the database column truncates at 500 chars. gyrus's episodic
schema stores the full message list from day one so the judge never needs
forensics.

## What this means

None of the four reversals weaken the thesis — the crown jewel is the credit
engine, and it's real. But every one of them would have been discovered
mid-port at 10x the cost, or worse, silently built around (a `vector(768)`
schema copied from a column nothing ever populated). The handoff's SOURCES.md
demanded "read these before reinventing anything"; the corollary it earned
today is *read these before believing the summary of them*.

## Related

- [ADR-0001](../adr/0001-port-not-rebuild.md) — the port decision this verifies
- [ADR-0002](../adr/0002-tier-by-signal-source.md) — the thesis, confirmed portable
- [SOURCES](../references/SOURCES.md) — the provenance map that was checked
