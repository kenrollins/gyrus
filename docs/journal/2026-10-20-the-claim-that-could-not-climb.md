---
id: journal-037-the-claim-that-could-not-climb
type: journal
title: "The claim that could not climb"
date: 2026-10-20
visibility: public
tags: [adr-0014, thesis, control, retrieval, consolidation, deploy]
related:
  - adr/0014-measure-against-a-control
  - adr/0002-tier-by-signal-source
one_line: "Ken asked whether the premise was achievable or theater; the answer was that the success curve borrowed from gemma-forge cannot be observed on an agent whose tools already succeed 97% of the time — so the claim was rewritten around a withheld-recall control, and the seventeen defects that had been corrupting the store's own numbers were fixed and deployed in the same session."
principle: "When the measurement cannot move, the thesis is not waiting for data; it is waiting for a different measurement. Build the control before building more features."
---

Ken's question after the review: *are we able to achieve our premise, or is
this vibe-code theater?* The honest answer was neither. The engineering was
real; the measurement was borrowed from a domain it does not fit.

## Why the curve could not climb

gemma-forge's 20% → 90% existed because STIG remediation started at 20% with
a hard verdict per rule. Pip's tool calls succeed about 97% of the time, a
followed-and-succeeded recall writes +1.0, and `0.5 + credit` caps at 1.00
after three samples. Since 2026-08-31 the store has 86 followed procedural
recalls on 16 memories and one negative outcome. Nothing in that can climb,
and nothing in it can tell good advice from bad. "The curve needs usage"
had been the comfortable reading for two months.

ADR-0014 replaces the measurement, not the tiering. One in eight eligible
prefetches (`recall_control_every`, never cron, never a warm-up) is computed,
logged with `withheld = true`, and returned empty. Every completed turn now
records `meta->'outcome' = {ok, fail, retries, served, withheld}`, where a
retry is a tool failing and the same tool being called again in the turn —
a cost that varies even when the turn ends in success. The claim holds if
served turns retry and fail less than withheld ones. The second number is a
monthly human grade of sampled recalls (relevant / harmless / wrong), the
August audit's hand count made recurring. Both tools live in `tools/`.

## What shipped under it

Two recreates, 36 tests, all of the review's load-bearing findings:

- **Demand is earned.** Cron sessions and warm-up fetches no longer log
  retrievals (`log=0`, `cron_*` guard). Migration 0009 recounted
  `recall_count` from distinct non-cron events: the cron bookkeeping that
  topped the store at 354 recalls now reads ≤ 24. The eviction guard is
  windowed (45 days without a recall) instead of "ever recalled", and a
  memory whose outcome credit says it is bad can leave regardless.
- **Ranking.** Candidate pools are drawn per family, so a 78%-knowledge
  store cannot fill all three legs before the 0.6 weight applies; "what is
  the kaiju ollama setup" now returns Ken's own Kaiju facts instead of four
  knowledge rows. Entities on more than 5% of live memories ("ken") are out
  of the graph leg. A dash-prefixed token no longer becomes a tsquery NOT.
- **Transient state.** A deterministic gate gives location and presence
  chatter a one-day clock; the nine live "phone is back home / N miles from
  coordinates" facts (one at 200 recalls, confidence 1.00) were retired.
- **Open loops age.** 45-day default clock, refreshed on re-mention; 465
  loops older than 45 days that nobody had mentioned again were retired,
  89 re-mentioned ones got a fresh clock. 587 live → 122.
- **Reconciler reach.** Same-claim folds now cross the personal tiers and
  include procedural (folds only — a text judge still never overrules
  outcome credit); the nightly pair budget is split by family so knowledge
  backlog cannot starve personal pairs.
- **Hardening from the code review.** The extraction consumer survives a
  DB error; the outcome sweeper stamps every exit and orders its queue (53
  dead turns were 147 short of silencing it again); the judge no longer
  escalates a yes/no to the 900 s lane and an unanswered judge earns no
  credit; a fenced `[]` is an answer; the graph cursor pages on
  `(updated_at, id)` ahead of the 20,000-row cliff; the firehose gate holds
  its cursor when the embedder is down.

Ken's two calls, same session: the Vitals per-drink and per-dose records
"do not belong in this" — a deterministic gate (substance + quantity or
clock time) now drops them at extraction and the 14 in the store were
retired; and the provider was replaced on shadesmar (1.2.0, `log=0`
warm-ups) with a gateway restart. Still his to decide: what the knowledge
tier is for (2% ever recalled, 16 ever browsed); the re-tier spot check;
the dream-pass lock order.

## Left as a prediction

Written before the data, per STYLE: by mid-November the control report
should show tens of turns in each arm with a procedural recall. My bet is
that served turns show fewer retries but not fewer failures — memory tells
Pip *which* command, and the failures that remain are environmental. If the
arms are indistinguishable, the procedural tier is decoration for this
workload and the honest next step is to say so.

Measurements in this entry: store queries 2026-10-20 00:30–02:00 UTC inside
the gyrus container; deploys at 01:24 and 01:45 UTC; probes via
`/v1/prefetch?log=0`.
