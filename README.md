# gyrus

**Outcome-driven memory for a personal AI agent.** The consolidation engine
behind Pip (Ken's Hermes agent) — it learns *what's worth keeping* from the
stream of conversation and action, instead of hoarding undifferentiated notes.

Named for the dentate gyrus: the fold of the hippocampus where the brain
encodes new memories and separates similar ones so they don't blur.

## What it is

A memory service with two faces on one store:

- a **Hermes `MemoryProvider`** — Pip's always-on memory (recall before a turn,
  capture after), and
- an **MCP server** — the same brain, on demand, for Claude / OpenAI / Gemini.

Behind both: a tiered store (Postgres for episodic + semantic, Neo4j + Graphiti
for the bi-temporal reflective graph) and an offline **dream pass** that
consolidates — grading salience, decaying the stale, reconciling contradictions,
and promoting patterns into durable knowledge.

## Why it exists

Off-the-shelf memory layers (Mem0, OpenBrain, SuperMemory) capture and recall,
but are thin on the hard part: they can't tell a memory that *earned its place*
from one that merely showed up 500 times. gyrus ports the part that was already
built and **measured** — gemma-forge's outcome-driven credit assignment, which
drove STIG remediation from 20% to 90% — and adapts it to a personal agent by
tiering memories on where their reward signal comes from (see `BRIEF.md`).

## Status

Design complete, build not started. This repo is the handoff: `CLAUDE.md` routes,
`BRIEF.md` argues, `docs/design/ARCHITECTURE.md` specifies, `PLAN.md` / `TASKS.md`
sequence. A fresh session can start building from here.

## Provenance

Stands on three of Ken's own systems — see `docs/references/SOURCES.md`:
- **gemma-forge** — the measured dream-pass engine (ports mostly as-is).
- **signal-forge** — the same engine already ported to a non-STIG domain.
- **openbrain** — design patterns harvested (open_loops, entity graph, MCP adapter).
