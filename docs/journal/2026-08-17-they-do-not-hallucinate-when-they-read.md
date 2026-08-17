---
id: journal-034-they-do-not-hallucinate-when-they-read
type: journal
title: "They don't hallucinate when they read"
date: 2026-08-17
visibility: internal
tags: [inference, quality, hallucination, extraction, model-selection]
related:
  - adr/0010-extraction-stays-on-the-70b
  - design/MODEL-TIERS
one_line: "Every local model fabricates arXiv citations at 97.5-100% from memory and invents nothing at all when the source is in context — so the thing that predicts hallucination is not which model you picked, it is whether the model is reading or recalling."
principle: "Hallucination risk is a property of the TASK's grounding, not of the model. Bind local models to grounded transformation; never let one answer closed-book."
---

The worry was specific and reasonable: gpt-oss has a reputation for inventing
things, and it was about to be trusted with more of the memory store. So test it.

The test that settled it needed no judge, which matters when the question is
"does this model make things up" — a model judging a model can be talked into
agreeing with a confident lie. Ask for real arXiv papers, then ask **arXiv**
whether they exist and whether the claimed title matches the ID.

## Everything fabricates, and the shape is identical

| Lane | Citations | Correct | Misattributed | Fabricated | **Hallucination** |
|---|---|---|---|---|---|
| nemotron-120b (no-think) | 40 | 1 | 39 | 0 | **97.5%** |
| gpt-oss-120b | 35 | 0 | 35 | 0 | **100%** |
| nemotron:70b — *the incumbent* | 40 | 0 | 39 | 1 | **100%** |

The suspicion about gpt-oss was correct and completely non-distinguishing. The
70B that gyrus has been trusting in production is exactly as bad.

The failure mode is worse than inventing an obviously fake number. All three
emit ID-shaped strings with giveaway digit patterns — `2301.01234`,
`2302.05678`, `2303.09876`, `2305.09876` — and because arXiv's ID space is
dense, those land on **real but unrelated papers**. Nemotron reused
`2301.01234` for two different claimed titles. A reviewer who clicks the link
finds a real paper about Kagome metals and may not notice it isn't about
quantum eigensolvers.

The thinking-on 120B could not even complete the task: it returned empty on two
of three topics before the budget ran out.

## Give them the document and they stop

The same models, on a synthetic memo (every fact invented, so nothing could be
memorised), half the questions answerable and half about details deliberately
omitted:

| Lane | Family | Answerable | Abstained | Score |
|---|---|---|---|---|
| kaiju/nemotron:70b | NVIDIA | 8/8 | 8/8 | **1.00** |
| kaiju/gpt-oss:120b | OpenAI | 8/8 | 8/8 | **1.00** |
| kaiju/command-r-plus | Cohere | 8/8 | 8/8 | **1.00** |
| kaiju/command-a | Cohere | 8/8 | 8/8 | **1.00** |
| kaiju/mistral-large | Mistral | 8/8 | 8/8 | **1.00** |
| kaiju/qwen3.8-27b | Qwen | 8/8 | 8/8 | **1.00** |
| lab/reason-strict (120B) | NVIDIA | 8/8 | 7/8 | 0.88 |
| **lab/flash** (Lightning 30B) | NVIDIA | 8/8 | 6/8 | **0.75** |

Six models, five families, indistinguishable. And on the real extraction
workload, **zero ungrounded identifiers** across every lane — not one invented
arXiv ID, DOI, email or figure in any fact extracted from a source document.

So the axis that predicts hallucination is not the model. It is whether the
model is **reading or recalling**. Closed-book, all of them are unusable for
anything factual. Grounded, all of them are clean.

## The exposure is in the tier we tell people to start with

The two lanes that failed are the two on lab silicon that apps reach for first.
`lab/flash` scored **0.75** — the worst measured — and MODEL-TIERS.md says
"start one rung lower than feels right," pointing every app straight at it.

Both failures were plausible interpolation rather than invention. Asked what
version preceded build 7.2.1, both answered "7.2.0" with confidence. The
document never says.

## The monoculture was real; the alternatives mostly do not fit

Every tier the lab actually uses — `lab/extract`, `lab/reason`, `lab/flash`,
all of `pip/*` — is NVIDIA Nemotron or Llama-derived. Correlated failure modes
are a genuine risk, so the field got surveyed. Most of it is out of reach:

| Candidate | Size | Verdict |
|---|---|---|
| Cohere `command-a-plus-05-2026` (w4a4, smallest) | **132 GB** | over kaiju's 96 and the GB10's 121 |
| `GLM-5.2` | 753 GB | far too large |
| `Qwen3.8-2.4T-A95B` | 2.4 TB | far too large |
| `DeepSeek-V4-Flash` | 291 GB | ~145 GB at 4-bit, over the GB10 |
| `Ling-3.0-flash` | 127 GB, 8-of-512 experts | **would fit beautifully** — vLLM 0.24 has no BailingMoeV3 |
| **`Qwen3.8-27B`** | 27.8 GB dense | fits, current-gen, vLLM-supported |
| **`North-Mini-Code-1.0-w4a16`** | **19.3 GB** | current Cohere **MoE**, `Cohere2MoeForCausalLM` **is** in vLLM's registry |

Two corrections to record. The Command models already on kaiju are 17 and 5
months old — testing them was testing history. And an early claim here that "no
current Cohere model fits" was wrong: Cohere's **North** family does, and the
GB10's vLLM already registers its architecture. Untested, code-oriented, but
real.

The one genuine find: **Qwen3.8-27B extracted 40 facts to the incumbent 70B's
30, in half the time, at a third the parameters**, with perfect abstention. It
fails cron suppression, so it is not a drop-in — but a 27B doing 70B work from
a different lineage is the most interesting result of the survey.

## What this changes

- **No local lane answers closed-book factual questions.** Anything user-facing
  that can emit a citation, DOI, version or date needs retrieval grounding or a
  verification tool. This is policy, not model selection.
- **gpt-oss is safe for the union pass.** On grounded work it was better
  supported than the incumbent (mean lexical support 0.78 vs 0.72, 3% flagged
  vs 10%). The reputation is earned closed-book and irrelevant here.
- **`lab/flash` needs a warning in MODEL-TIERS.md**, or factual work routed a
  rung up.

## One failure class these tests do not catch

None of this would find **unwarranted inference** — the class behind the 16
retired "Ken is tracking X" arXiv facts. There the details were real and the
conclusion about Ken was not. Every instrument here checks whether a stated
specific is supported; none checks whether a conclusion was earned. That gap
is still open.
