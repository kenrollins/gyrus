---
id: journal-023-the-band-cosine-cannot-judge
type: journal
title: "The band cosine cannot judge"
date: 2026-08-16
visibility: public
tags: [audit, dedupe, threshold, pattern-separation, bench, prompt-lineage]
related:
  - adr/0010-extraction-stays-on-the-70b
  - adr/0012-model-shape-indirection
one_line: "The 0.90–0.93 near-dup band graded ~80% rewordings / ~20% genuinely distinct facts differing by one critical token — so the threshold stays and the dream pass gets a discriminator; same session re-verified the prompt-lineage numbers (~93% keep, 0 noise) and caught the wrong-tier defect living in the current prompt, not just the backlog."
principle: "Where one token carries the meaning, no similarity threshold exists that both merges rewordings and preserves distinctions — stop tuning the number and adjudicate the pair."
---

Two measurements were still open after the cleanup: whether 0.93 is the right
dedupe threshold, and whether the prompt-lineage quality claims survive an
honest instrument. Both closed today, and both closed with a twist.

## The threshold was never the question

Post-cleanup rescan (10,966 rows): the ≥0.93 population is down from 187
pairs to 24 — all chain artifacts (fold B into A, and C's nearest neighbour
becomes A) that a second sweep pass converged to zero (23 more merges, store
10,943). The write-path gate and the sweep agree with each other now.

That left the 0.90–0.93 band: 952 pairs the system deliberately keeps. A
seeded 30-pair sample, both facts read side by side:

- **~80% are the same claim reworded** — the union pass's two engines
  phrasing one insight two ways, or Ken restating a preference across
  sessions. Under ADR-0002 these should fold as corroboration.
- **~20% are genuinely distinct facts wearing near-identical sentences**:
  "Ken is the decider for ADR-0024" vs "…for ADR-0018". `pip install .` vs
  `pip install .[test]`. `foam-note-link` vs `foam-placeholder-link`.
  "Dell Federal insights" vs "Dell relevance charts" in a report request.

The distinct pairs share a signature: total lexical overlap except one
critical token, usually an identifier or a number — exactly the token a
1024-dim sentence embedding rounds away, and exactly the distinction a
memory named after the dentate gyrus exists to preserve. Lowering the
threshold to 0.90 would merge ~190 of these. So the number stays at 0.93,
and the open question turns into a design task instead: a **band
discriminator** in the dream pass — for nearest pairs in 0.90–0.93,
adjudicate same-claim vs distinct before folding. Deterministic first
(differing digit/identifier tokens → distinct, which clears most of the
graded examples), `lab/flash` for the remainder. Tracked in TASKS.md.

## The lineage numbers survive; the prompt's tier sense doesn't

`bench_lanes.py` on the production shape (`lab/extract`, six goldens,
v1.2): 6/6 windows, 37 facts, 192.8s — matching ADR-0010's engine-level
numbers through the new shape name, which is also the indirection's
end-to-end proof. Grading the 37:

- Non-cron windows: 27 facts, **zero structural noise, ~93% keep** — the
  discredited-instrument era's "96%, 0% noise" claim roughly survives
  re-measurement. The lineage narrative was right even though its numbers
  were unverifiable.
- **~20% of non-cron facts file relayed world knowledge as `factual`**
  ("Q-NEXT is a National QIS Research Center at Argonne"). The store
  audit's wrong-tier finding is not just pre-ADR-0006 backlog — it is live
  prompt behaviour, which means yesterday's re-tier sweep is a recurring
  chore until the prompt learns the knowledge-tier boundary. Folded into
  the same future golden-set pass as the cron fix.
- Cron windows still extract (6 and 4 facts where the right answer is
  zero), including Ken's email address out of a scheduled brief. Fresh
  confirmation, defect unchanged, worker filter still the only guard.

## The boundary worked like a boundary

The thalamus audit ran in parallel today, fed by a consumer-observed
findings file (`docs/THALAMUS-FINDINGS-2026-08-16.md`) rather than by
opening its repo. Outcome worth recording: adapter path exclusions deployed
upstream (the refill flank closes), `published_at` verified faithful for
email and arXiv (so ADR-0011 has clean event dates waiting), and github —
which shipped no dates at all — now carries last-commit dates, opening a
backfill path for event-time on the stored github facts. Two audits, one
contract file, zero coupling.
