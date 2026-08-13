---
title: gyrus
hide:
  - navigation
  - toc
---

# gyrus

!!! quote ""
    **Pip's memory — outcome-driven consolidation that learns what's worth keeping
    instead of accumulating noise.**

    By **Ken Rollins**, Federal Field CTO — Emerging Technologies at Dell.

---

The dentate gyrus is where the brain encodes new memories and performs *pattern
separation* — telling similar experiences apart so they don't blur. That is this
service's job: turn the ordinary stream of an agent's conversation and tool use into
durable, distinguishable memory, and consolidate the signal out of the noise.

gyrus is the memory system behind **Pip**, a personal AI agent. It is a Hermes
`MemoryProvider` that ports a *measured* consolidation engine — the "dream pass" proven
on hard ground truth in a prior project — and applies it to a personal agent by tiering
memories on where their reward signal comes from.

!!! quote ""
    Most memory layers are good at capture and recall and thin on everything that makes
    memory *useful over time*: decay, contradiction, salience, and any notion of an
    **earned** memory. gyrus is the earning.

## The claim it proves — and how you'd falsify it

> Outcome-driven memory consolidation transfers to a *personal* agent by tiering memories
> on their signal source. Where a memory has a hard outcome — a command that worked — the
> machinery ports untouched. Where it doesn't — a preference — an honest proxy replaces
> it. The result learns what to keep instead of drowning in what merely recurred.

You falsify it by pointing a real agent's memory at gyrus and measuring the **procedural**
tier: does the agent's tool-success-on-recall climb over sessions? If earned memories
demonstrably raise success and cut retries, the transfer holds. If they don't, the thesis
is wrong — and we learn exactly where. That test, honestly, is [still ahead](journal/index.md).

## Tier by signal source

The crux of the whole system. A personal agent seems to have no reward signal — but its
memory splits three ways, each with a *different* one, and only one is truly signal-starved.

| Tier | Examples | Reward signal |
|---|---|---|
| **Procedural** | a command that worked, a tool quirk, a config fix | **true ground truth** — reuse → run → pass/fail |
| **Factual** | project facts, entities, who-relates-to-what | contradiction + corroboration |
| **Preference** | how the user likes to work | proxy only — corrected? reused? uncontradicted? |

Transfer the machinery unchanged; **swap the evaluator per tier.** That is why the port
works where a generic memory layer can't: it never had a ground-truth tier to anchor scoring.

## What this deliberately is not

- **Not a vector database with a chat wrapper.** Retrieval is hybrid — keyword, semantic,
  and an entity graph, fused — never vector-only, because vector similarity collapses on
  superficially-similar technical strings.
- **Not a raw-document store.** gyrus keeps *distilled insight*; deep-document search is a
  separate tier and a separate project.
- **Not a finished result.** The consolidation framework is validated on real data; the
  falsifiable procedural claim is not yet proven. The [journal](journal/index.md) says so plainly,
  as it goes.

Every claim here is measured, decided in an [ADR](decisions/index.md), or marked as still-ahead —
and says which.
