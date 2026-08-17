---
id: journal-033-the-least-flexible-box-should-hold-the-busiest-model
type: journal
title: "The least flexible box should hold the busiest model"
date: 2026-08-17
visibility: internal
tags: [inference, platform, extraction, quantization, gb10, l4-fleet, kaiju]
related:
  - adr/0010-extraction-stays-on-the-70b
  - design/MODEL-TIERS
one_line: "A day spent asking why the GB10 wasn't winning ended with the fleet's real rule — match the model to the silicon's shape, and give the box that can't change its mind the workload that never stops — plus a blind fact-grading that kept the 70B workhorse and three quantizations that each failed differently."
principle: "Decode speed is set by ACTIVE parameters against memory bandwidth, not by the parameter count on the label; every other placement question follows from that."
---

The day opened with a reasonable complaint: the GB10 has 128 GB of unified
memory and vLLM, kaiju has two RTX 6000 Adas and ollama, and somehow every
observation said we were leaning on kaiju. Why isn't the expensive box winning?

It took until 3am UTC to answer properly, and the answer was not "the GB10 is
slow."

## The GB10 is an MoE machine and nothing else

The first benchmark compared what was actually deployed, which is a bad
comparison — Nemotron-3-Super-120B-A12B on the GB10 against a dense 70B on
kaiju. The GB10 lost single-stream decode (16.2 vs 19.4 tok/s) and won
everything else. That looked like a wash.

Running the SAME model on both boxes settled it. Llama-3.3-70B, 4-bit both
sides, 65536 context both sides:

| | kaiju (2x RTX 6000 Ada, ollama) | GB10 (vLLM, unified) |
|---|---|---|
| decode, 1 stream | **19.4 tok/s** | 5.5 tok/s |
| prefill | ~1,050 tok/s | **~1,465 tok/s** |
| aggregate @16 | 18.5 tok/s | **55.5 tok/s** |

Three and a half times slower per stream on identical weights. The GB10's
LPDDR5X runs roughly 273 GB/s against an Ada's ~960; decode is bandwidth-bound,
so a DENSE 70B reading ~38 GB per token tops out near 7 tok/s there. Measured
5.5, which is 76% of the theoretical ceiling — the hardware is working fine.

Which reframes the earlier "wash": Nemotron-3-Super is 120B total but activates
only 12B, so it reads a sixth the bytes. The label says 120B; the silicon only
cares about the 12B.

The prediction that follows: gpt-oss-120b activates ~5.1B, so 12/5.1 = 2.35x.
Written before the run. **Measured 2.46x** (38.6 vs 15.7 tok/s), and at 32
concurrent it sustained 326 tok/s against kaiju's flat ~19. You can now predict
a model's GB10 speed from its active-parameter count before downloading it.

## Three quantizations, three different failures

The extraction workload wanted to move to the L4 fleet. The same model —
Llama-3.1-Nemotron-70B, the incumbent — in three formats:

**FP8 (68 GB)** worked, but starved the KV pool to 68,704 tokens. The largest
golden window (~8k in + 8k out) overflowed `max_model_len` and returned HTTP
400. 5/6 windows, and the miss was the config's fault, not the model's.

**W4A16 (38 GB)** was the one worth remembering. It loaded clean, reported
`{"status":"loaded"}`, served `/health` and `/v1/models`, held all four GPUs at
99%, logged **19.5 tok/s of generation throughput and a 49.9% prefix-cache hit
rate** — and answered "Reply with the single word OK" with:

```
 other other other other other other other other other other...
```

forever. Every automated signal the lab watches was green while the model
emitted pure noise. Forty minutes of benchmarking went into discovering that,
and only because a human read the output. Had it reached `lab/extract` on those
numbers it would have written noise into the memory store at a window a minute.

**AWQ-INT4 (40 GB)** won: 6/6 windows, 32 facts in 150.0s against kaiju's 30 in
386.1s, 22.7 tok/s decode, 246 tok/s aggregate at 16 concurrent, and a 270,080
token KV pool at the full 65536 window.

A hypothesis that was wrong and worth recording: I blamed W4A16's garbage on
vLLM's Marlin kernel path, and pinned `--quantization awq` to avoid it. AWQ then
logged `Using MarlinLinearKernel` and worked perfectly. Marlin was not the
culprit; that specific compressed-tensors checkpoint was. The fix worked for the
wrong reason.

## The gate that a health check cannot replace

W4A16 produced [lane-contract-probe.py](../../../dmz/tooling/lane-contract-probe.py):
three checks — does the lane terminate, follow a one-word instruction, and hold
a JSON shape. Seconds to run.

It earned itself back the same night. A Lightning FP8 build looked like a pure
win for the flash tier — 157 tok/s against BF16's 110, half the weights, a 3.7M
token KV pool, tool-calling verified. It passed everything, went into
production, and the gate caught `pip/reason-fast` on the next sweep: with
thinking ON it never terminates. **34,980 characters of reasoning, empty
content, at a 12,000-token cap**, on "return the three primary colors." Rolled
back inside a few minutes.

The probe's limit is equally worth stating: it validates correctness, not
capacity. It passed both engines of an L4 co-residency attempt that then died
under real load.

## Turning thinking off is engine-specific, and getting it wrong looks like incompetence

Three separate times a model looked broken and was merely misconfigured. The
mechanism is not portable:

| Engine | Honours | Ignores |
|---|---|---|
| vLLM | `chat_template_kwargs: {enable_thinking: false}` | `think` |
| ollama | `think: false` | `chat_template_kwargs`, and a `/no_think` suffix |

Measured on qwen3.8: `chat_template_kwargs` and a `/no_think` suffix both left
reasoning fully on; `think: false` cut a trivial answer from 95 tokens to 10.
Before that was found, qwen3.8 scored 0 facts on all six golden windows and
looked like a model that could not follow an output contract. It was a flag.

This is the same class of error [ADR-0010](../adr/0010-extraction-stays-on-the-70b.md)
exists to document, and it produced a third false verdict the same day: the
GB10's 120B "failed" extraction at 3/6 windows until someone noticed no GB10
lane had ever pinned thinking off. With it off: 6/6 and **37x faster**
(3,605.9s to 98.5s).

## The workhorse stays, and the blind grade is why

With gpt-oss looking strong it was tempting to move `lab/extract` onto it. The
grading was done blind — lane labels stripped, both lanes' facts interleaved
under one shuffled numbering, answer key sealed until verdicts were committed,
because the person grading had recommended one of the lanes.

80 facts:

| Lane | Facts | KEEP | Wrong-tier | DROP | keep-rate |
|---|---|---|---|---|---|
| gpt-oss-120b | 50 | 45 | 3 | 2 | **90%** |
| kaiju/nemotron:70b | 30 | 27 | 3 | 0 | **90%** |

Dead even on precision; gpt-oss finds 67% more. Its two DROPs include a real
factual error — it claimed "Gmail OAuth on the Windows box is authenticated"
where the source says the *agent's* box, not Ken's locked-down laptop.

But ADR-0010's bar is coverage, not volume, and it fails: **13 of 27** of the
incumbent's KEEP facts have a semantic match in the candidate. The two models
extract largely disjoint sets. That independently reproduces the ADR-0010
addendum from the other direction (64 of gpt-oss's 65 facts survived the 0.93
dedupe against the 70B's). They are complementary, which is exactly why the
two-pass union design is right — and why the workhorse does not move.

## The rule the whole day was circling

The fleet was allocated backwards. Over 30 days:

| Role | Home | Requests |
|---|---|---|
| Extraction workhorse | kaiju (**on-demand**, pays ~50s reloads) | **4,242** |
| Embeddings | kaiju (on-demand) | 3,759 |
| Flash lanes | **L4 fleet (always-resident)** | **969** |
| Union pass | kaiju (on-demand) | 693 |

The least flexible, always-warm box was hosting the 969-request bursty tier,
while the 4,242-request steady tier sat on the on-demand box paying a reload
every quiet spell.

Two rules fall out, and they are the day's actual product:

1. **Match the model to the silicon's shape.** Sparse MoE and long context to
   the GB10; dense models and single-stream latency to kaiju's Adas; the L4s
   are the best prefill-per-watt in the building and extraction is
   prefill-bound.
2. **The box that cannot change its mind gets the workload that never stops.**
   Flexibility and steadiness are complementary resources — spend them against
   each other, not with each other.

## Where it stopped

Not finished, and worth saying plainly. Moving extraction to the L4s requires
rehoming flash, and both candidate homes failed for different reasons:

**L4 co-residency** — CUDA OOM at 29.81 MiB free. Per card: 22.03 GiB total,
AWQ 9.54, Lightning FP8 7.63, leaving 4.86 GiB for two engines' KV,
activations, cudagraphs and NCCL all-reduce scratch. Both engines loaded, both
passed the contract probe, then every real window died. The scratch is invisible
to either engine's memory profile.

**GB10 co-residency** — better odds, since `tensor_parallel_size=1` means no
cross-GPU traffic and no NCCL scratch at all. The memory fit (81 of 121 GiB with
both attempted). It failed on something else entirely:

```
ValueError: `layers_block_type` contains invalid types:
{'linear_attention', 'full_attention'}
```

The GB10 runs a pinned `vllm-lab:26.07-xg`; the L4s run `vllm/vllm-openai:latest`
and serve that architecture without complaint. Per-model image support plus
validating a newer vLLM on Blackwell is its own careful job.

One more mamba-hybrid trap found on the way: Nemotron-3-Super allocates one
Mamba cache block per decode slot, so `max_num_seqs` must scale with
`gpu_memory_utilization`. At 0.62 there were 45 blocks against a hardcoded 64
and the engine refused to start. That knob is now per-model rather than baked
into the orchestrator.

Both orchestrators also gained `POST /reload` — they read `models.yaml` only at
startup, so registering a model meant a restart, and a restart re-bootstraps
residents. That cost four unnecessary 10-minute reload cycles before it was
fixed.

Tracked as backlog #16 and #17. The measurements are done; what remains is a
placement decision and an image upgrade, not another benchmark.

## Addendum, same day: it landed, via the model nobody had to fight

The entry above stopped with the cutover blocked. It isn't any more, and the
unblock was a smaller idea than the one being forced.

Path A was "get Lightning onto the GB10," which needs per-model image support
and a newer vLLM validated on Blackwell. Path B asked a different question:
**does the GB10's current image already serve something that can do the flash
job?** It did — `qwen35-a3b` (Qwen3.6-35B-A3B NVFP4, 21 GB, ~3B active), whose
own registry description had read "Flash lane: MoE 3B-active — near-dense
quality at flash decode" since it was staged. The weights were already on disk.

Gated before repointing anything:

| check | result |
|---|---|
| contract probe | PASS |
| flash perf bar (>=40 tok/s) | **77.4 tok/s**, TTFT 0.105s |
| tool calling | correct call, matches the incumbent |
| thinking ON terminates | **finish=stop with real content** |
| co-resident under load | **16/16 and 8/8 at 5.4k tokens, zero errors** |

That fourth row is why `reason-fast` survived. The plan had been to collapse it
onto the 120B, because Lightning FP8's thinking never terminated. Qwen's does,
so the fast-thinking tier stayed a fast tier instead of taking a 7x latency hit.

The fifth row is the one that mattered. The L4 co-residency attempt passed a
contract probe and then died on every real window; this time both engines were
driven simultaneously with 5.4k-token prompts and neither dropped a request.
**Single-GPU co-residency works where tensor-parallel co-residency did not** —
no NCCL all-reduce scratch to eat the margin invisibly.

The honest cost: one GPU timeshares compute, so under simultaneous heavy load
flash fell from 77.4 to 4.4 tok/s. Acceptable at 969 req/mo of bursty traffic,
and worth revisiting if that grows.

Final placement, measured on the live lane rather than a bench alias:

| Box | Model | Serves |
|---|---|---|
| L4 fleet | Nemotron-70B **AWQ-INT4**, resident | `lab/extract` |
| GB10 | nemotron-120b **+ qwen35-a3b** | reasoning, flash, reason-fast |
| kaiju | catalogue, nothing pinned | embeddings, vision, union pass |

`lab/extract` through its new home: **32 facts / 149.8s / 6-of-6 windows**
against kaiju's 30 / 386.1s. 2.6x faster, 0% ungrounded identifiers, 1.00
abstention, and the ~50s reload is gone because it is resident. Same weights as
ADR-0010 chose, so no quality question was reopened.

One near-miss worth recording: the first `lab/extract` repoint carried the
**W4A16** repo id — the build that emits `" other other other"` forever and was
deleted hours earlier. Caught before the gateway restart. The lesson is not
"be careful"; it is that two 4-bit builds of one model differed only by a
substring in a config, and one of them is poison. The contract probe would have
caught it, which is the argument for running the gate on every repoint and not
only on new lanes.

## Operational findings from the same session, recorded so they don't evaporate

Three that are not about placement but came out of buttoning it up.

**Both engines were running at HALF their native context windows.** The L4
Lightning at 65536 and the GB10 120B at 131072, both native 262144. That was
not a tuning choice, it was inherited — and it was actively breaking things.
Hermes sets a global `max_tokens: 16384`, so a 65536-window lane hard-fails any
prompt over 49,152 input tokens. Found live in the logs:
`background_review` died on **49,153 + 16,384 = 65,537 against a 65,536
ceiling** — off by one token. Both raised to native; the KV pools had ample
headroom the whole time (L4 1,448,526 tokens at 5.5x concurrency, GB10
6,957,443 at 25.9x). The lesson is that a context ceiling and an output cap
interact, and neither number means anything alone.

**A reasoning model was doing mechanical work.** Hermes' `compression` slot was
bound to `pip/reason` — the GB10 120B with thinking ON, at 15.7 tok/s the
slowest lane in the lab, spending ~69% of every response deliberating about how
to compress something. Moved to a new `pip/reason-strict` (same engine, thinking
pinned off): **8.33s -> 2.12s and 129 -> 31 tokens** on the same prompt, 3.9x
faster for a quarter the tokens. Four more slots
(`triage_specifier`, `kanban_decomposer`, `profile_describer`, `monitor`) moved
from `reason-fast` to no-think `pip/fast` on the same reasoning: classification
does not need deliberation.

**Pip's main conversational slot moved to Codex over OAuth**, with local
silicon inverted from primary into the fallback, so she degrades to the GB10
rather than going dark. Conversational traffic leaves the LiteLLM ledger by
deliberate choice — a fully operational agent was judged worth more than
complete spend tracking, and the 17 auxiliary slots still cover every mechanical
call. Worth recording a correction: an earlier claim here that device-code OAuth
was outside OpenAI's terms was **wrong**. `auth_type: oauth`,
`source: manual:device_code` is the sanctioned "Sign in with ChatGPT" path for
Codex, billed against the subscription rather than per-token API credits. The
config had it wired as a first-class provider all along.

Also checked and found to be a non-issue: **thalamus makes no gateway calls at
all** — no key, nothing in the ledger. It is the ingestion boundary; gyrus does
every model call. There was never a second service grabbing models.

The hallucination and model-survey findings from this session are their own
entry — see [journal-034](2026-08-17-they-do-not-hallucinate-when-they-read.md).
