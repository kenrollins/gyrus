---
id: journal-028-tense-as-truth
type: journal
title: "Tense as truth"
date: 2026-08-16
visibility: public
tags: [m6, reconciler, contradiction, open-loops, dream-pass]
related:
  - adr/0002-tier-by-signal-source
  - adr/0011-event-time-grounding
one_line: "The M6 reconciler shipped into the nightly dream pass — same-claim folds, contradiction supersession, and open-loop resolution in one capped stage; its first committed pass folded 44, superseded 3 contradictions ('IS 5527 commits behind' losing to 'WAS ... before the rebase'), and closed 32 stale loops with evidence pointers."
principle: "Fold, keep, supersede, resolve — four verdicts, one question asked of every close pair: do these two memories still agree about the world?"
---

M6's boxes — contradiction detection, preference correction, loop closure —
and the band discriminator's promotion into the dream pass turned out to be
one build, because they are one question asked of nearest-pair candidates:
do these two memories agree? `reconcile.py` answers it four ways: **same**
(fold as corroboration), **distinct** (keep both), **contradicts**
(supersede, newer event wins), **resolved** (a later memory closes the
loop). Double agreement with order swap gates every destructive verdict;
disagreement always keeps; everything is capped per run and rides the
nightly dream sweeper.

One semantics change from the standalone band tool, learned by looking at
what a contradiction IS: a token-conflict pair ("backup_keep is 3" /
"backup_keep is 5") can no longer be auto-ruled distinct — the same
sentence-shape with a different value is either two facts or a live
contradiction, and only reading decides. Only one-sided enumerations stay
deterministically distinct.

The first committed pass, dry-run inspected before applying:

- **44 same-claim folds** from 136 judged pairs (the band regrows from
  union-pass rewordings; nightly capping keeps it mowed).
- **3 contradictions superseded**, and the best one names the entry: "The
  Hermes repository IS 5527 commits behind origin/main" lost to "…WAS 5527
  commits behind before the rebase." Same numbers, same subject — the
  tense is the truth, and event-time ordering picked the right survivor.
  The others: a schema version fact (2.1.2 → 2.2) and a gemma-forge run
  metric corrected by its more precise sibling.
- **32 of 100 stale loops closed**, each retired with `superseded_by_id`
  pointing at the memory that resolved it — "does `hermes sessions prune`
  need a TTY?" closed by the memory stating it doesn't, which is also the
  memory the M3 harness proved true by running it. Two duplicate loops
  asking the same question both closed on the same evidence. The remaining
  ~330-loop backlog drains at ≤100 a night.

Store: 10,505 → 10,428. Every reconciler action is a soft retire with a
pointer to what superseded it — the bi-temporal rule holds even when the
system is disagreeing with itself.

For the preference tier this is ADR-0002's "corrected" proxy delivered by
the same engine: a newer preference that contradicts an older one now
supersedes it instead of coexisting with it. The confidently-wrong
preference — the failure mode the ADR named at the start — finally has a
correction mechanism that doesn't wait for Ken to notice.
