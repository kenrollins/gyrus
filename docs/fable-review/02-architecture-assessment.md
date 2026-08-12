# 02-architecture-assessment

_(empty — Fable writes here; flush after every finding)_

## The M3 credit-assignment seam: SOUND, but not "1:1" [CONFIRMED]

Verified `memory_retrievals` against the real credit SQL in
`/data/code/gemma-forge/gemma_forge/dream/pass_.py:159-195`. The column contract
matches exactly: gyrus `outcome_value, outcome_confidence, followed_llm,
followed_emb, followed_computed_at` are the direct analogues of gemma-forge
`outcome_value, outcome_confidence, tip_followed_llm, tip_followed_emb`. The
follow-aware CASE math (1.0 / 0.3 / 0.5 modifiers, mean→signal via 2*mean-1)
will read gyrus's columns without change. Good — the hardest thing to get right
is right.

TWO corrections to the "ports 1:1" framing in seed notes / ADR-0001:
1. **Grain differs.** gemma-forge assigns credit per `work_items.category`
   (`JOIN work_items wi ON wi.item_id = tr.rule_id ... GROUP BY wi.category`).
   gyrus has no category and no rule_id; the natural grain is per-`memory_id`.
   The consumption SQL must be REWRITTEN to `GROUP BY memory_id` — a small,
   isolated change, but it is not a copy-paste. This is the "swap the evaluator"
   work the project always said remained; just naming it precisely.
2. **No run scoping.** gemma-forge scopes a pass with `WHERE tr.run_id = %s`.
   gyrus `memory_retrievals` has no run/batch column. Idempotency is still
   covered — `WHERE followed_computed_at IS NULL AND outcome_value IS NOT NULL`
   (the existing partial index `idx_retrievals_pending` already targets exactly
   this) — so a pass processes all unscored retrievals and marks them. Adequate;
   just confirm M2 uses that predicate rather than importing run_id semantics.

Verdict: the foundation M3 needs is present and correctly shaped. Proceeding to
M2 does NOT risk a foundation rewrite on this axis. The schema decision (review
target #3) is validated.

## Does M1 hold the thesis? PARTIALLY — one leak (see F4)

The tier discriminator, per-tier provenance, corroboration counter, and the
retrieval-outcome seam are all in place: the machinery ADR-0002 needs exists.
The leak is F4 — a large `assistant_suggested` domain-knowledge population with
no signal source, which the tiering neither scores nor prunes. The thesis
survives (the honest labeling holds) but the store is not yet "learning what to
keep about Ken"; it is also accumulating a knowledge base the design scoped out.
M2's consolidation MUST address F4 or the M3 success curve is measured against
diluted ground.
