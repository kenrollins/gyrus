---
id: journal-032-the-gate-that-died-of-success
type: journal
title: "The gate that died of success"
date: 2026-08-17
visibility: public
tags: [relevance-floor, firehose, adr-0012, bench, overnight]
related:
  - adr/0008-earned-value-retention
  - adr/0012-model-shape-indirection
one_line: "The overnight chain validated the last untested number from the audit brief and found the firehose relevance gate had been a no-op — every arxiv item cleared 0.55 because a 10k-memory store resembles everything — replaced with fixed profile anchors that split relevant from irrelevant cleanly; the same night, the lab's model re-engineering passed its ADR-0012 golden-set check without gyrus changing a line."
principle: "A similarity gate scored against a growing corpus measures the corpus, not the candidate — reference points that must not drift have to be fixed by construction."
---

Ken re-engineered the lab's model fleet and went to bed; the overnight
chain had three phases and a rule for their order: verify the instruments
before using them.

## Phase A/B: the shape contract earns its keep

The smoke watcher waited out the re-engineering (stable by 03:00), then ran
the ADR-0012 golden-set bench — mandatory after any night the engines
might have moved. Result: gyrus's three shapes still bind to the same
engines, and behavior matches baseline (6/6 windows, 30 facts, cron
suppression holding on BOTH lanes — the union lane now returns [] on cron
windows in under 3 seconds). The entire fleet re-engineering happened
without gyrus changing a line or a config: the indirection working exactly
as designed, verified rather than assumed.

## Phase C: the no-op gate

The 0.55 firehose floor was the last "never tested, and load-bearing"
number from the original audit brief. The test found something better than
a wrong threshold: **all 469 arxiv items scored ≥ 0.593** against the
store. The gate rejected nothing, and had likely rejected nothing for
days — max-cosine against a store that grew from 2.5k to 10k+ diverse
memories saturates, because everything AI-adjacent resembles *something*
in a big enough memory. The gate was calibrated against the small store of
its birth and died of the store's success. Only the top-12 cap was doing
real filtering, silently.

The graded sample (n=16 — small, and stated everywhere) put numbers on
the damage: ~31% of accepted items strictly relevant.

## The fix: reference points that cannot drift

Score candidates against **fixed profile anchors** — Ken's interest
profile as four embedded sentences — instead of the store. Anchors can't
saturate; the store's growth no longer inflates every candidate's score.
Validation on the graded sample: clean split, min(relevant)=0.653 vs
max(irrelevant)=0.606, where store-scores had them interleaved. Floor
moved to 0.60 against anchor scores; the cap stays as volume control; the
anchors carry a comment requiring re-validation whenever Ken's focus
shifts them.

The general lesson joins the harvest list: the audit already knew
confidence-without-outcome-contact is seniority; this is the corollary for
gates — similarity-to-what-you-know measures how much you know, not
whether you should learn the new thing. Novelty detection and relevance
detection need different reference frames, and only one of them is
allowed to grow.

(Also in the night's ledger: three stale nemoclaw-era facts retired on
Ken's direct correction; the scheduled dream sweeper turns out to be due
this afternoon, not last night — its 24h clock started from yesterday's
manual run, and claiming its first autonomous cycle a half-day early would
have been exactly the unverified-automation zero this journal keeps
warning about.)
