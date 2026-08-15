---
id: journal-021-the-epidemic-that-did-not-replicate
type: journal
title: "The epidemic that didn't replicate"
date: 2026-08-15
visibility: public
tags: [audit, dedupe, measurement, verification]
related:
  - adr/0010-extraction-stays-on-the-70b
one_line: "The brief's '15% of the store is duplicates' shrank to 1.5% under a full-store exact scan; 95% of real pairs predate the ivfflat fix, and the embed-outage dedupe skip is real but accounts for ~10 pairs — the scary number was the instrument again."
principle: "A measurement you didn't reproduce is a rumor with digits — even when it comes from the session that taught you that lesson."
---

The audit brief's most consequential store claim: a 400-memory sample found
15% of memories with a same-tier neighbour at or above 0.93 — production's own
dedupe threshold. It came with a confirmed mechanism (`persist()` skips the
near-duplicate check when the embedder returns no vector) and a to-do:
measure how much of the 15% came from that path before fixing anything.

The measurement came back with a different headline: **the 15% does not
replicate.**

Full-store scan — every live memory's nearest same-tier neighbour among
earlier rows, exact (`ORDER BY embedding <=>`, no index), run twice
independently with identical results:

- **187 pairs at ≥0.93** — 1.5% of the store is an undeduped later twin;
  ~3% of rows are touched by a pair.
- Replicating the brief's own 400-sample method (nearest neighbour, either
  direction): **2.5%**, not 15%. Mean nearest-neighbour similarity 0.811, not
  0.849. The old numbers are ~2–6× inflated across every threshold. The
  ad-hoc SQL that produced them is unrecoverable (`q.py` was just a statement
  runner), so the diagnosis stops at: instrument artifact, unreproducible,
  discard.

## The pairs that do exist have a clean stratigraphy

| mechanism | pairs | share |
|---|---|---|
| created before migration 0003 (blind ivfflat dedupe, 28% recall) | 177 | 95% |
| embed-outage dedupe skip (#9) + close races | 10 | 5% |
| same-transaction batches, no vector | 0 | 0% |
| same source_key (post-0006 independence rule) | 0 | 0% |

The duplicate problem is almost entirely **historical**: rows written on
08-12/08-13 while the dedupe check ran through an ivfflat index that missed
~72% of true nearest neighbours (journal-015 territory, fixed by migration
0003). Everything after the fix — the github day, the entire email ingest,
gateway restart included — produced essentially no ≥0.93 pairs.

The brief's #9 mechanism is nonetheless real, and the scan caught its
footprint: at 2026-08-15 03:01:52, one extraction call (turn 823) inserted
three facts sharing a timestamp, each a near-twin of an existing memory —
a whole persist batch whose embed had failed, sailing past the check exactly
as the code reads. Total damage from that mechanism across the store: about
ten pairs. Ken's backpressure ruling (fail loudly, don't insert undeduped)
stands as cheap insurance on the write path — but it is insurance, not triage.

## What this changes

1. "~15% of the store is duplicates; memory counts measure nothing" softens
   to: counts are soft by ~2%, and the dream pass's 0.97 merge backstop,
   lowered to 0.93 for one run, would fold the 177 legacy pairs.
2. The real open question was never the bug — it is the **0.90–0.93 band**:
   1,045 pairs of the same-claim-reworded kind (union-pass phrasings live
   here), which the threshold, not any failure, chooses to keep.
3. The brief warned that every number in it was a lead, not a result — then
   its scariest number failed reproduction by an order of magnitude. The
   lesson wasn't hypothetical. The scan and classifier now live in
   `tools/store-audit/` so the next session reproduces instead of inherits.

(Also closed while in the neighbourhood: the fallback lane's 300s timeout —
`chat_json` now gives `vllm/nemotron-120b` its own 900s ceiling
(`extract_fallback_timeout`), so the kaiju-outage safety net stops failing on
real window sizes. ADR-0010 addendum, TASKS.md.)
