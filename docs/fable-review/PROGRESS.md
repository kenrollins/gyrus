# PROGRESS — Fable review of gyrus M1

Update after EVERY finding. Assume termination mid-sentence.

## Status: COMPLETE (Fable, 2026-08-12 evening)

**Independence caveat, on the record:** this review runs in the SAME session that
built M1 (model switched to Fable in place). The reviewer carries the author's
context and rationale — a confirmation-bias risk. Compensations: every claim is
re-verified from disk/database this session; the evaluation work uses held-out
data and adversarial probes the build never ran; findings that would embarrass
the build are explicitly in scope (two already queued from first re-inspection:
broken turn-level provenance on backfill memories, and unaudited ANN recall).

| Phase | State | Notes |
|---|---|---|
| Read MISSION + 00-seed | done | content verified against disk |
| Measurements (store audits, retrieval eval, seam check) | in progress | |
| 01 code findings | in progress | flushing as found |
| 02 architecture assessment | pending | |
| 03 retrieval + extraction evaluation | pending | |
| 04 handoff queue | pending | |

## Log
- 2026-08-12 — seeded by the building session.
- 2026-08-12 — Fable start. Independence caveat logged. Measurement plan:
  (a) provenance [DONE F1], (b) assistant_suggested audit [DONE: F4 HIGH — 27% of store is domain KB not user-memory],
  (c) ANN recall vs exact scan [DONE: 28% recall@10 — F2 HIGH], (d) websearch-or [DONE: verified correct],
  (e) held-out eval [DONE: hit@5=92% w/ ANN bug present, MRR .73], (f) M3 seam [DONE: SOUND],
  (g) near-dup [DONE F5], (h) auth [DONE F3].
