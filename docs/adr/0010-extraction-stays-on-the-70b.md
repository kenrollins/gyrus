# ADR-0010: Extraction stays on `kaiju/nemotron:70b`; the fast lane is not a candidate

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Ken (brief), verified by measurement

## Context

The lab's inference review (2026-08-15) flagged gyrus as the largest consumer
on the gateway — ~14.9M tokens, ~$63 hyperscaler-equivalent — doing its
heaviest work on its slowest lane: `kaiju/nemotron:70b` at 8.5 tok/s and 65s
p50, the slowest thing gyrus calls. It noted gyrus has `vllm/nemotron-
lightning-l4` and `lab/flash` scoped at ~75 tok/s and has never used them, and
asked for a measured comparison before accepting the status quo — roughly 9x
on paper.

`extraction.py` already asserted the opposite, and had since M1: *"the flash
tier extracted almost nothing (dry-run #2 and #3). Prompt design won; the big
model does not."* That sentence is why the workhorse was never revisited.

**The prior evidence does not support the claim it was making.** Re-reading the
six result files behind it:

| window | recorded | what it actually was |
|---|---|---|
| conference-cleanup | `ok=False`, 0.2s | HTTP failure — never reached a model |
| day3-summaries | `ok=False`, 0.3s | HTTP failure — never reached a model |
| cron-quantum-radar | "NO JSON", 0 facts | **empty response** |
| recent-other | "MALFORMED JSON" | content was `[ERROR: Agent failed … API returned None]` |
| cron-monday-brief | 0 facts | correct-ish; the 70B was *also* recorded 0 |
| nqisrc-panel | 1 fact, 5.6s | the only real datapoint |

The cause is now confirmed: that run addressed `vllm/nemotron-lightning`, a
model id this key returns **403** on. The lane it meant to test is
`vllm/nemotron-lightning-l4`, which answers in 0.1s. The claim was never
tested — it was a misconfiguration recorded as a quality verdict.

Worse, the harness's `\[.*\]` regex silently scored real output as zero. The
70B's "0 facts" on `cron-monday-brief` was a parse failure over a reply that
plainly contained facts. **Both** models were undercounted, so the whole
golden-set matrix — including the keep-rate and noise figures quoted in
`extraction.py`'s prompt lineage — rests on an unreliable instrument.

## Decision

**Extraction stays on `kaiju/nemotron:70b`.** The fast lane is not a candidate
for the extraction pass. This is now a measured decision rather than an
inherited sentence.

`lab/flash` and `vllm/nemotron-lightning-l4` are the **same backend** — byte-
identical facts and per-window latencies matching to 0.1s across all six
windows. Treat them as one lane; prefer the `lab/flash` name (tier indirection).

## Evidence

Re-measured 2026-08-15 with `tools/extraction-eval/bench_lanes.py`, which
drives the **production** path — real v1.2 SYSTEM prompt, real balanced-brace
salvage parser — with the fallback model disabled so no lane is silently
answered by another, and every lane warmed first (kaiju is on-demand).

| lane | windows usable | facts | total s | speed |
|---|---|---|---|---|
| `kaiju/nemotron:70b` | 6/6 | 37 | 193.0 | 1.0x |
| `vllm/nemotron-lightning-l4` | **4/6** | 63 | 101.5 | 1.9x |
| `lab/flash` | **4/6** | 63 | 101.4 | 1.9x |

Three findings, in order of weight:

1. **It stops following the output contract.** On `nqisrc-panel` and
   `recent-other` the fast lane returned conversational prose instead of JSON
   — *"Got it. I've recorded the tonal preference as a durable setting…"*.
   Zero usable facts on two of six windows, including the richest one
   (`nqisrc-panel`: the 70B returns the ecosystem-shift, hybrid-HPC and
   modularity insights that journal-016 was written about).

2. **It misfiles tiers, and it misfiles them into the tier that matters.** On
   `day3-summaries` it returned 34 facts to the 70B's 8, and classified
   "Q-NEXT / Argonne Quantum Foundry provides a full-stack workflow", "MICCoM
   collaboration with Giulia Galli", and "high-throughput first-principles
   calculations" as **procedural**. Those are world knowledge. Under ADR-0002
   the procedural tier is the one carrying gemma-forge's outcome-driven credit
   assignment — the tier where the thesis is actually falsifiable. A lane that
   fills it with conference facts does not just add noise, it corrupts the
   measurement the project exists to make. Its 34 facts also included 7
   "preferences" from a single conference-summary window, against a prompt
   whose entire purpose is discernment.

3. **The 9x does not survive contact with the workload.** End-to-end the fast
   lane is **1.9x**, not 9x, and on `day3-summaries` it was not faster at all
   (37.6s vs 37.1s). The tok/s advantage is a *decode* number; these windows
   are 12–24k characters of input, so wall-clock is prefill-dominated. This is
   the general correction: for long-context, short-output work, decode
   throughput is close to irrelevant.

The original claim was directionally right and factually wrong. The fast lane
does not extract "almost nothing" — it extracts *plenty*, and badly.

## Consequences

- The workhorse is unchanged, so nothing in the hot path moves.
- `extraction.py`'s docstring is corrected to cite this ADR instead of
  asserting a measurement that was never taken.
- `bench_lanes.py` replaces `extract_dryrun.py` for lane comparison. The older
  script keeps its frozen v0 prompt and weak parser, which is precisely why it
  cannot be trusted for this question.
- **The prompt-lineage numbers in `extraction.py` are unverified.** The
  keep-rate and noise figures come from the same broken instrument. Re-running
  the golden set under `bench_lanes.py` is now open work, tracked in TASKS.md.
- **Cron suppression does not work on either lane** — a discovery this bench
  made visible rather than caused. The prompt says automated output must yield
  nothing; on `cron-monday-brief` the 70B returns 6 facts and the fast lane 13,
  the latter attributing the cron job's own generated brief to `ken_said`. The
  live path is protected by `worker._extract_turn`'s `platform='cron'` filter,
  so this is defense-in-depth today, not an active leak. Tracked separately;
  fixing the prompt requires its own golden-set pass.
- Revisit if a lane appears with instruction-following in the 70B's class. The
  bench is now cheap and honest, so revisiting costs ~5 minutes of GPU time.
