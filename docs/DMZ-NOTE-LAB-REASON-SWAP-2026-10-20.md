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

## Still open: are the new model's thinking-off facts good enough?

The 35 vs 15 comparison is ungraded. Ken grades the side-by-side sheet
(KEEP / DROP / WRONG-TIER per fact, plus MISSED). When that lands, gyrus
adds here: keep-rate and wrong-tier rate per engine, and a verdict on
whether the fallback stays on `lab/reason-strict` after the swap or should
move. Until then the fallback is on the strict lane, which is the right
place under both outcomes: if the new model's facts grade well, nothing
changes; if they grade as noise, the fallback moves and this note says where.
