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

## Addendum (same day): the two 120B lanes, and what the union pass costs

The first pass compared the 70B against the fast lanes only, and repeated the
inherited "the 120B lost domain facts" line without testing it. That claim came
from ONE window on the **v0** prompt, against `vllm/nemotron-120b`; the matrix
run that followed scored that lane `0 (thinking ate budget)`, `HTTP 400`,
`truncated JSON`, and three windows never run. It was never a measurement. Note
also that gyrus has **two** 120B lanes and the docs conflate them:
`vllm/nemotron-120b` is the *fallback*; `kaiju/gpt-oss:120b` is the *union
second pass*, which runs on every extraction.

Re-measured at `max_tokens=8000` (so a thinking model is not scored on its
budget), same production path, fallback disabled:

| lane | windows usable | facts | total s |
|---|---|---|---|
| `kaiju/nemotron:70b` | 6/6 | 35 | 190.5 |
| `vllm/nemotron-120b` | **2/6** | 13 | 1787.4 |
| `kaiju/gpt-oss:120b` | 6/6 | 65 | **145.2** |

**The configured fallback does not work.** `vllm/nemotron-120b` hit the 300s
`chat_json` ceiling on four of six windows — the 301.6s entries are timeouts,
not slow successes. The lane that exists to cover a kaiju outage would itself
fail on real window sizes. Either its timeout needs raising well past 300s, or
the fallback should point at a lane that can answer inside one.

**The union pass earns its place, and is not the expensive half.** gpt-oss:120b
finished *faster* than the 70B and returns the reference layer the original
n=1 note claimed — speaker rosters, `DOI 10.1038/s41578-021-00306-y`, contact
addresses — which the 70B walks past. That justification now rests on six
windows instead of one.

**But the two models barely overlap, and the dedupe threshold cannot tell.**
Of gpt-oss's 65 facts, **64 survive production's own 0.93-cosine dedupe against
the 70B's 35** — a 2% absorption rate. Inspection shows some survivors are the
same claim reworded ("Hybrid quantum computing combined with HPC is now
considered…" vs "Hybrid quantum + HPC is now core, not side dressing"). Both
are stored. A 400-memory sample of the live store finds **61 (15%) with a
same-tier neighbour at ≥0.93**, and 143 (36%) at ≥0.90 — duplicates the
system's own rule says should not exist.

The likely mechanism is in `extraction.persist`: the near-duplicate check is
guarded by `if pgvec is not None`, so whenever the embedder is unavailable —
which the code explicitly expects under backfill load — dedupe is skipped
entirely and the fact inserts unconditionally. `_embed_sweeper` supplies the
vector afterwards, so the memory looks deduped forever after. Same failure
shape as the rest of this ADR: an unavailable dependency degrading a result
into something that looks correct. Tracked in TASKS.md; not fixed here,
because the right threshold is itself an open question.

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
