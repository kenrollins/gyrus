# To dmz: gyrus's position on the GB10 `lab/reason` swap

Written 2026-10-20 for the dmz project (gb10-supervl REPORT §6, item 4).
Counts and mechanism only; the graded facts stay in gyrus's private goldens tree.

## Decision already taken on the gyrus side (deployed 2026-10-20 00:21 UTC)

gyrus's extraction fallback no longer points at `lab/reason`. It points at
**`lab/reason-strict`** (same GB10 engine, `enable_thinking: false` set by the
gateway lane), with gyrus's existing 8,000-token budget and 900 s per-window
client timeout. So the swap's medium-effort default on `lab/reason` does not
reach gyrus at all, and the per-window ceiling question is answered on
gyrus's side (900 s, under the lane's 1,800 s upstream timeout).

Why: nothing in gyrus ever pinned thinking off, and `lab/reason` carries no
pin, so the deployed fallback had been running a reasoning model with
thinking on against a JSON-array task. The dmz bake-off's medium-thinking
row (2/6 windows, 0 facts) is what the fallback would have become on swap
day. Thinking off, the candidate completed 5/6 windows at the harness's
300 s ceiling with its slowest at ~280 s, inside 900 s.

Also fixed in the same deploy: gyrus's *union* pass (second-opinion
extractor on kaiju) used to fall through to `lab/reason` when its own lane
failed. That is what the ledger's "137 gyrus calls to lab/reason in 30 days"
were (they track `lab/extract-union`'s failures day for day, 09-20 → 10-06).
The union leg now runs with no fallback. Expect gyrus's `lab/reason` traffic
to go to zero and its `lab/reason-strict` traffic to be rare (primary-lane
outages only).

## What gyrus needs from dmz on swap day

1. Keep `lab/reason-strict` as a lane on the new engine with
   `enable_thinking: false` and the 1,800 s upstream timeout, `num_retries: 0`.
2. Nothing else. No new lane is requested.

## Golden-set evidence (prompt v1.5, six windows, fallback disabled)

| Engine, lane condition | Budget / ceiling | Windows ok | Facts | Total |
|---|---|---|---|---|
| Nemotron 3 Super 120B, thinking off (today's `lab/reason-strict`) | 8,000 / 900 s | 6/6 | 23 | 141.8 s |
| same, dmz bake-off row | 4,000 / 300 s | 6/6 | 15 | 112 s |
| Nemotron 3.5 Super VL, thinking off | 4,000 / 300 s | 5/6 | 35 | 793 s |
| Nemotron 3.5 Super VL, medium thinking | 4,000 / 300 s | 2/6 | 0 | 1,281 s |

The 8,000 / 900 s row was run 2026-10-20 inside the gyrus container through
the gateway with the gyrus key; the other three are dmz's 2026-10-17 runs.

## Verdict: the new model's thinking-off facts are not noise, but a third are mis-tiered

Graded 2026-10-20 (Claude pre-graded every fact against its golden window;
Ken reviews seven soft calls). KEEP = grounded, durable, right tier.
WRONG-TIER = worth keeping but filed in the wrong tier. DROP = not a memory
or not supported by the window.

| Engine (thinking off, prompt v1.5) | Facts | KEEP | WRONG-TIER | DROP | Keep-rate | Wrong-tier rate | Keep-or-retier |
|---|---|---|---|---|---|---|---|
| Nemotron 3 Super 120B (today's `lab/reason-strict`) | 15 | 15 | 0 | 0 | 100% | 0% | 100% |
| Nemotron 3.5 Super VL (candidate) | 35 | 20 | 12 | 3 | 57% | 34% | 91% |

What the numbers hide:

- **The incumbent's 100% is precision without recall.** Across four
  real windows it extracted zero facts about Ken himself (his obligations,
  colleagues, addresses, open follow-ups) and one fact from a window whose
  panel transcript held five. Its KEEP set is a strict subset of the
  candidate's on every window both completed.
- **The candidate's wrong-tier errors are one systematic mistake.** All
  twelve are conference content (speakers, session themes, talk claims)
  filed as `factual / ken_said` instead of `knowledge / relayed`, the exact
  personal-vs-world GATE prompt v1.5 spells out. The content is right; the
  tier is wrong. In gyrus that matters: the factual tier scores on
  corroboration, the knowledge tier on utility decay (ADR-0002/0006), so a
  mis-tiered fact is scored by the wrong signal.
- **Two of the three drops are harmless, one is a real error:** an inference
  the window does not support (it had Ken working *on* an internal app he is
  in fact required to *use*). One wrong fact in 35.
- **Speed:** ~7x slower; the largest window timed out at the harness's
  300 s and should fit gyrus's 900 s, but that is a prediction, not a
  measurement, until the lane is re-benched on the new engine.

**Recommendation: the fallback stays on `lab/reason-strict` after the swap.**
No better candidate exists on non-L4, non-kaiju silicon with thinking off
and a JSON contract, and kaiju's 70B is already the gateway's own fallback
for `lab/extract`. Two conditions, both gyrus's to run:

1. After the swap, `bench_lanes.py --models lab/reason-strict --max-tokens
   8000 --timeout 900` on the golden set: require 6/6 windows inside 900 s
   and cron windows 0/0. If the conference window still times out, the
   per-window ceiling (`extract_fallback_timeout`) goes up; the lane does not
   move.
2. gyrus accepts a ~1-in-3 mis-tier rate from the fallback *during primary
   outages only* and tracks it: a post-extraction GATE check (re-tier
   conference/relayed content filed as factual) is a gyrus task, not a lane
   choice. Until then the fallback's facts are a known contaminant of the
   factual tier for the duration of an outage, which is the right trade
   against extracting nothing.

Nothing further is requested from dmz. The graded sheet stays in gyrus's
private goldens tree.
