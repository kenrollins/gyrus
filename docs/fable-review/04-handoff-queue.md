# 04 — Handoff queue (ranked, for the Opus session after Fable)

Reviewer ran in the build session (Fable-in-place); independence caveat in
PROGRESS.md. Every item below is measurement-backed this session. Severity =
impact on the falsifiable claim, not code aesthetics.

## DO BEFORE M2 (foundation — cheap now, expensive later)

1. **[HIGH] Fix the ANN index (F2).** Drop `idx_memories_embedding` — at
   2.5k–50k rows a flat scan is <10ms and 100% recall, vs measured 28% recall@10
   today. One migration. Fixes the semantic leg AND write-time dedupe (F5) in one
   move. Re-run every semantic measurement afterward. Effort: S. Do this first.

2. **[HIGH] Decide the F4 knowledge-vs-memory split.** ~27% of the store is
   domain knowledge (`assistant_suggested`, no personal anchor, no signal source).
   Either (a) add a session-level "user teaching me vs. me recording the world"
   gate to extraction, or (b) add an explicit reference tier retrieval weights
   down, or (c) commit M2's dream pass to evicting "no corroboration + no recall +
   no personal anchor". Without one, M3's success curve is measured against ~27%
   inert ballast. This is a DESIGN decision for Ken, not a mechanical fix. Effort:
   M–L. Highest-leverage item in the review.

3. **[MED] Re-run the backfill to completion, cron-excluded.** 465 turns remain
   `extracted_at IS NULL` (author's container restarts). Idempotent now; safe.
   Then backfill turn-provenance (F1) is still NULL for the historical corpus —
   accept as degraded, or thread turn_ids through `extract-window`. Effort: S.

## DO DURING M2 (consolidation must own these)

4. **[MED] Dedupe becomes a consolidation concern (F5).** Even with F2 fixed,
   window-overlap dupes will recur; the dream pass should merge near-dups and
   fold their corroboration counts, rather than trusting write-time cosine.

5. **[MED] Provenance for transcribed content.** Conference-note facts are
   labeled `assistant_suggested`/`factual` but are really `relayed` domain
   knowledge. The `relayed` value exists (55 rows use it) but the extractor
   under-applies it. Tighten the prompt or add a session-type signal.

## DO BEFORE M5 (the MCP face leaves the LAN)

6. **[MED] Auth (F3).** Full store is readable unauthenticated on the DMZ today.
   Fine for LAN v1; a hard blocker for the MCP face. Scoped token, LAN-side now.

## VALIDATED — no action (recorded so it isn't re-litigated)

- The M3 credit-assignment seam is sound; `memory_retrievals` matches
  gemma-forge's contract. Rewrite the credit SQL to `GROUP BY memory_id` (not
  category) and scope with `followed_computed_at IS NULL`. Not a foundation risk.
- Held-out retrieval: hit@5=92%, MRR=0.73 WITH the ANN bug present — hybrid
  redundancy is real and carried a broken leg. Expect it to improve after F2.
- The tolerant-JSON salvage, cron filtering, and the synchronous-prefetch
  deadline are all correct and measurement-justified.

## Bottom line
The foundation is sound where it is most expensive to be wrong (the M3 seam).
The two HIGH items (F2, F4) are both fixable before M2 without a rewrite: F2 is a
one-line index change, F4 is a design decision. Recommend: fix F2, decide F4 with
Ken, finish the backfill — THEN start M2. Nothing found warrants reworking M1.
