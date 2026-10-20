---
id: journal-035-the-fallback-that-answered-for-the-second-opinion
type: journal
title: "The fallback that answered for the second opinion"
date: 2026-10-19
visibility: internal
tags: [extraction, fallback, gateway, model-selection, verification, gb10]
related:
  - adr/0010-extraction-stays-on-the-70b
  - adr/0012-model-shape-indirection
  - design/MODEL-TIERS
one_line: "The 137 lab/reason calls the ledger attributes to gyrus's 'extraction fallback' were almost all the union pass failing over, day for day, with thinking on and an 8,000-token budget — so the GB10 bake-off, run thinking-off at 4,000 tokens, measured a lane gyrus has never actually run."
principle: "A fallback is a code path, not a config value. Before you bench what a fallback 'does', find the calls it actually made and trace them to the caller that fell."
---

The dmz project is swapping the model behind `lab/reason` on the GB10 (Nemotron 3
Super 120B to Nemotron 3.5 Super VL 120B) and asked for gyrus's view first, since
`lab/reason` is gyrus's extraction fallback. They had already run our own
`bench_lanes.py` on the six golden windows, thinking off, at the harness's
default 4,000-token budget and 300 s ceiling. The question they asked was sharp:
does the fallback run with thinking pinned off, and if not, does the bench
understate its cost?

## What the code says the fallback does

Nothing in gyrus pins thinking off in production. `chat_json` only sends
`chat_template_kwargs` when a caller passes `template_kwargs`, and the only
caller that does is the lane bench's `--no-think` flag. The gateway definition
for `lab/reason` carries no `enable_thinking` either (the strict lane does).
So the production fallback runs the 120B **with thinking on**, against a task
whose output is a JSON array.

The budget is not the bench's 4,000 either. `extraction.extract()` defaults to
8,000 tokens for every lane (the 2026-08-16 fix for the thinking model starving
at 4,000). The clock is 900 s client-side for the fallback attempt
(`extract_fallback_timeout`), under the gateway's 1,800 s upstream timeout.

So the bench ran thinking-off / 4,000 / 300 s and production runs thinking-on /
8,000 / 900 s. Those are different lanes in everything but name. The bench
measured what `lab/reason-strict` would do; nobody has yet measured what the
fallback as deployed does.

## Who actually fell

The ledger said 137 `lab/reason` calls from the gyrus key in 30 days. The
container's own logs only reach back to its 2026-10-06 recreation, so the
lifetime counters in the spend exporter (Prometheus keeps 30 days) had to
stand in. Sampled daily from 2026-09-20, the `lab/reason` counter moved by
+110 to 2026-10-07 and then by +1 (2026-10-09) — and stopped.

Laid beside the `lab/extract-union` counter, the increments match almost day
for day through 2026-10-03 (7/9, 5/5, 6/6, 7/7, 3/4, 4/3, 3/4, 3/2, 5/5,
16/18, 10/18, 5/4, 9/9). `chat_json` builds the same candidate list for every
caller — the requested model, then `extract_fallback_model` — so when the
union lane (gpt-oss:120b on kaiju's Ollama) failed or returned nothing
parseable, the *second opinion* was answered by the 120B on the GB10,
thinking on, and its facts merged into the store as the union pass's.

The primary lane did not need the fallback: the only post-recreation
failures in the log are two union-lane connection failures on 2026-10-06
and one union 500 on 2026-10-09, which account exactly for the counter's
last movements. From 2026-10-06 ~20:00 UTC the union lane has been healthy
and the fallback has not fired at all.

Two things follow. First, "4% of the slot's calls" is not the cost of a
safety net for `lab/extract`; it was the cost of a flaky second-opinion lane
for about three weeks, paid on the slowest silicon in the lab with its
reasoning switched on. Second, the facts in the store from that period
carry a provenance the design did not intend: the union field says
gpt-oss:120b; the author was the 120B thinking aloud.

## Two things seen in passing

- The outcome sweeper has failed every three minutes for as far back as
  the container's log reaches (2026-10-06 17:49 UTC). `tool_outcome`
  regexes over `m["content"]`, and some tool content arrives as a list of
  typed blocks.
- The outcome judge (`lab/flash`) has made no calls in 30 days.

**Correction, same day (2026-10-19, later session).** The first draft of
this entry blamed the Hermes v0.21.5 provider shipped in that recreation.
Wrong: the store holds six turns with list-shaped tool content, all from
Pip's zulip vision tool, the first dated 2026-08-17 — weeks before that
provider. Four of them sit in the sweeper's pending queue (the earliest
2026-08-31). `score_pending` ran the queue in one try/except, so the first
unscoreable turn ended the pass, and the same turn came first next time.
The store's own numbers date the silence: procedural recalls were
`followed_computed` every week through 2026-08-31 and never again. Seven
weeks, not thirteen days — the log horizon was the container's, not the
bug's. And that is the whole answer to the judge question: no turn got far
enough to need one.

## What changed, three commits

Ken's call after reading the above, in this order, each on its own commit:

1. **The second opinion never falls back.** `chat_json` grew a `fallback`
   switch and the union leg runs with it off. A down union lane now skips
   the second opinion — warning, `gyrus_union_skipped_total` — rather than
   being answered by the fallback and merged under the union's name. Dry
   run against the live gateway with a nonexistent union lane: two models
   called, neither the fallback.
2. **Fallback thinking pinned off by lane, not by flag:**
   `extract_fallback_model = "lab/reason-strict"`, budget and timeout
   unchanged. Golden pass on today's engine at the production budget
   (8,000 tokens, 900 s), in the container, fallback disabled: 6/6
   windows, 23 facts, 141.8 s; cron windows 0/0. The same engine at the
   bench default (4,000 / 300 s) gave 15 facts in 112 s, so the extra
   budget buys facts, not just time.
3. **The sweeper reads content blocks** (`content_text`, shared with the
   window renderer) **and one turn's failure is one turn's loss**, not the
   pass's. The patched functions ran over all six list-content turns in the
   store without error; 29 tests pass.

**Deployed 2026-10-20 00:21 UTC** (recreate, two hours before the 02:15
burst, queue empty). The first sweeper pass ran at 00:23: 200 turns, 57
outcomes written, 0 failed, and the former poison turn scored like any
other. The `lab/flash` judge took its first calls in seven weeks (417 →
623 on the ledger within the pass). `gyrus_union_skipped_total` reads 0.
The note to dmz is `docs/DMZ-NOTE-LAB-REASON-SWAP-2026-10-20.md`.

## What this changes for the swap

The question for dmz is not "does Super VL extract more facts than the
incumbent thinking-off" (it does: 35 vs 15 on five windows, ungraded). It is
whether the fallback should move to `lab/reason-strict` (thinking off, the
condition the bench actually measured) with a longer per-window ceiling, or
stay on a lane that will, after the swap, think at medium effort and — on the
bench's evidence — time out on four of six windows before writing a single
fact. The grading sheet decides the first half; the second half is already
decided by the medium-effort row: 0 facts in 1,281 s.

The facts themselves stay out of git. The three result files and the
side-by-side sheet live in the container until Ken copies them to the
gitignored goldens tree; the sheet builder (`compare_sheet.py`) is the only
new thing in the repo.

## The grades, and what precision hides

Ken declined the sheet — fairly: "that's what I have you for" — so the
grading was done here, every fact against its own golden window, with seven
soft calls flagged for him. The incumbent scored 15 of 15 KEEP, 0 wrong
tier. The candidate scored 20 KEEP, 12 WRONG-TIER, 3 DROP of 35: a 57%
keep-rate, 91% keep-or-retier.

The incumbent's perfect score is the interesting number. Across the four
real windows it produced no fact about Ken at all — not his weekly
obligation, not a colleague, not an address, not an owed follow-up — and
one fact from a window holding a five-point panel summary. It is precise
because it is timid. The candidate found the personal layer every time and
filed every conference claim under the wrong tier: twelve facts, all
`factual/ken_said` where the GATE says `knowledge/relayed`. One mistake,
made systematically. That is a prompt-compliance failure a re-tier pass can
catch; the incumbent's silence cannot be caught by anything.

So the verdict to dmz: the fallback stays on `lab/reason-strict` after the
swap, re-benched at 8,000 / 900 s on the new engine, with gyrus owning a
GATE re-check for the fallback's output. The extra facts were not noise.
They were mis-filed.

