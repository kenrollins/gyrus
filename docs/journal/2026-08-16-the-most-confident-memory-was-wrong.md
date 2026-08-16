---
id: journal-026-the-most-confident-memory-was-wrong
type: journal
title: "The most confident memory in the store was wrong"
date: 2026-08-16
visibility: public
tags: [m3, outcomes, curve, credit-assignment, harness, retier]
related:
  - adr/0002-tier-by-signal-source
  - adr/0011-event-time-grounding
one_line: "M3's loop closed end-to-end at scale: the store's single most confident procedural memory (1.00) gave dead advice, the harness proved it with real probe failures, credit assignment crashed it to 0.215, and recall re-ranked away — the thesis mechanism observed working, with its honest caveats recorded."
principle: "Confidence without outcome contact is just seniority. The falsifiable tier earns its name the first time its most confident member gets demoted by evidence."
---

Two jobs today: repair the re-tier sweep's reverse misfiles, then start M3
for real. The second one ended with the project's thesis visibly working.

## The 71 that came back

The context-aware re-check of the 1,031 factual→knowledge moves (this time
telling the classifier which systems are KEN'S — the first pass read "Hermes
version is v0.17.0" as world knowledge) returned 755 world / 71 personal /
27 ambiguous. All three known misfiles flipped; the 71 moved back to
factual; ambiguous stayed put, since moving needs positive evidence. The
baseline-2 extrapolation said ~180; the true count at n=853 was 71 — a
reminder that a 3-in-20 sample carries a wide interval.

## Building a fair examiner is most of the work

The M3 harness (tools/m3-harness/) drives real reuse loops: prefetch logs
recalls for a task-shaped query, the top procedural recall's own text is
parsed for the command it references, and a read-only probe runs on the Pip
VM. Turns post back through the real pipeline (`extract=false`, so the
harness can never pollute the store), and outcomes score through the real
writer — now with the LLM tip_followed judge (the M3 box left open on
2026-08-13) confirming or refuting the embedding leg.

Round one taught three fairness lessons, each now a comment in the code:
a non-login ssh shell's PATH failed a command that works in real sessions
(harness artifact scored as bad advice — wiped and re-run); `--help` probes
punish argparse-less scripts (`py_compile`/`sh -n` is the honest "the
procedure is real" check); and the judge REFUSED to count a script-existence
probe as following a *workflow* memory — which nulled my first attempt at a
negative signal and was exactly correct. The follow-gate protects memories
from unfair blame, including the harness's.

## The falsification

The probe hunt surfaced the perfect subject: memory 2114, **confidence
1.00, the most confident procedural memory in the store** — "For OpenBrain
promotion kinds, run `pip_openbrain_autopromote_candidates.py --json
--limit 8`". The VM has a `retired-openbrain` directory; the script is gone.
Maximum-confidence advice, structurally dead.

Three rounds of honest probes (locate and validate the script the tip
names): three genuine failures, judge-confirmed as followed. Credit −0.285
on 3 samples — the min-sample guard's exact threshold. Then the committed
consolidation, where earned outcome overrides every proxy:

| memory | before | after |
|---|---|---|
| 2114 (dead advice, conf 1.00) | 1.000 | **0.215** |
| 4172 (dead workflow) | 0.699 | **0.215** |
| 204 (`hermes sessions prune`, works) | 0.598 | **1.000** |
| 1909 (proactive-review script, works) | 0.680 | **1.000** |

Fifteen memories now carry ground-truth credit. Round 8 showed the
downstream effect: three of the four dead-advice tasks re-ranked their
recall away from the demoted memories. The fourth is the recorded caveat —
a near-verbatim query keeps 2114 on top because RRF keyword dominance beats
a 0.715× confidence multiplier; at 0.215 it is aging toward eviction, which
closes that gap the slow way. And its successors in recall (1144) fail
their probes too, correctly: ALL openbrain advice is dead, and the loop
learns that one memory per cycle.

## What is proven and what is not

Proven, at scale, on real infrastructure: recall → follow (embedding + LLM
judge) → genuine tool outcome → credit under the sample guard → confidence
movement → re-ranked recall. Every gear of the falsifiable claim, turning
together, including the direction nobody wants: the store's proudest memory
demoted by contact with reality.

Not proven, deliberately: the long-run CURVE — tool-success-on-recall
climbing across weeks of organic use. Eight harness rounds are dynamics
validation, not statistics (success-on-recall moved 43%→50% round-over-
round, n too small to mean anything). That number needs Ken actually using
Pip, which was always the plan's honest boundary.

(Also observed in the same consolidation: 6,038 knowledge confidences moved
down — ADR-0011's event-time decay touching real dates for the first time,
May-2024 repo docs finally scoring as two years old. And the store grew by
42 unattended: thalamus's first daily github run arriving through the
pipeline built yesterday, edited docs re-crossing with commit dates.)
