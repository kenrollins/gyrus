---
id: gotcha-no-think-mechanism-is-engine-specific
type: gotcha
title: "Turning thinking off is engine-specific, and the wrong field fails silently"
date: 2026-08-17
visibility: internal
tags: [inference, gateway, thinking, gotcha]
related:
  - design/MODEL-TIERS
  - adr/0010-extraction-stays-on-the-70b
one_line: "vLLM reads chat_template_kwargs.enable_thinking, ollama reads a top-level `think` field, and each ignores the other's — so a reasoning model told to stop thinking with the wrong field keeps thinking, burns the whole budget, and returns EMPTY content that scores exactly like a model which cannot follow an output contract."
---

## The mechanism

There is no portable way to say "do not think". It depends on the engine behind
the lane, and sending the wrong field is a silent no-op:

| Engine | Honours | Ignores |
|---|---|---|
| **vLLM** (GB10, L4 fleet) | `chat_template_kwargs: {"enable_thinking": false}` | `think` |
| **ollama** (kaiju) | top-level `think: false` | `chat_template_kwargs`, and a `/no_think` suffix in the prompt |

Measured 2026-08-17 on `kaiju/qwen3.8-27b` through the gateway, same prompt
("Return ONLY a JSON array of the three primary colors"), four variants:

```
plain                  tok=95   content=23   reasoning=362
chat_template_kwargs   tok=95   content=23   reasoning=362   <- ignored
/no_think suffix       tok=102  content=22   reasoning=373   <- ignored
think=false            tok=10   content=25   reasoning=0     <- works
```

## Why it costs a whole debugging session

A thinking model that never gets the flag spends the budget deliberating and
returns **empty content** with `finish_reason: length`. That is
indistinguishable, from the outside, from a model too weak to follow the output
contract — so the natural conclusion is "this model is bad" and the natural
action is to reject it.

That mistake produced **three** false quality verdicts in one day:

1. `qwen3.8-27b` scored **0 facts on all six** golden extraction windows. With
   `think: false` it scored **40** — more than the incumbent 70B's 30. It was a
   flag, not a model.
2. `vllm/nemotron-120b` "failed" extraction at 3/6 windows and 3,605.9s. No GB10
   lane had ever pinned thinking off; with it off, **6/6 and 98.5s — 37x**.
3. ADR-0010's original verdict, same class of error one layer down.

## The trap in the current config

The gateway pins `chat_template_kwargs` on the flash lanes — correct, they are
vLLM. It pins nothing on the ollama lanes. So **every thinking-capable model on
kaiju** (`gpt-oss:120b`, `gemma4:31b-q8`, `qwen3.8-27b`) is uncontrollable from
tier config alone; the caller has to send `think: false` itself.

## What to do

Send **both** fields when the engine is not certain. They are mutually ignored,
so there is no conflict:

```json
{ "chat_template_kwargs": {"enable_thinking": false}, "think": false }
```

And before concluding a model cannot follow a contract, check whether
`content` is empty while `reasoning_content` is long. That signature means the
budget ran out mid-deliberation — the model never got to the answer.

Note two models that take **neither** field: gpt-oss uses `reasoning_effort`
(low/medium/high), and Qwen3.6 honours `enable_thinking` in both directions
(verified: thinking ON terminates with real content, unlike Nemotron-3.5
Lightning FP8, which never stops).
