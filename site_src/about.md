---
title: About
---

# About

gyrus is built by **Ken Rollins**, Federal Field CTO for Emerging Technologies at Dell,
as a personal exploration of how a personal AI agent's memory should actually work — built
in a home lab, documented as it happens.

It is one project in a small lineage of home-lab systems that build on each other:
**gemma-forge** (the measured consolidation engine gyrus ports), **signal-forge** (the
precedent for porting that engine to a domain without hard ground truth), and the retired
**openbrain** (design patterns harvested). The [Sources](sources.md) page traces every
borrowed idea to where it came from.

## How to read this site

- **[The Claim](brief.md)** — what gyrus is, the falsifiable thesis, and what was rejected.
- **[Architecture](architecture.md)** — the full design.
- **[Decisions](decisions/index.md)** — the accepted ADRs, the *why* behind the shape.
- **[Journal](journal/index.md)** — the build as it happened, honest about what broke. Only
  entries written for a public audience appear here; the working log keeps more, including
  the mistakes that don't generalize.
- **[Sources](sources.md)** — provenance.

## The honesty rule

Two prior projects taught this one how to keep a journal. One published its build log
wholesale and over-shared — a reader met a wall of confessions before a wall of results.
The other under-recorded and let the reasoning evaporate. gyrus splits the difference with
a single rule, applied per entry: **our own errors appear when they teach something
general — framed as the finding, not as autobiography.** What you read here is chosen for
you deliberately; the rest stays in the repository where it belongs.

## Disclaimer

This is a **personal project.** It is **not** an official Dell product, a reference
architecture, a Dell position, or a statement on behalf of Dell Technologies or any
customer. Views and findings here are Ken's own. Nothing here is a security disclosure,
a benchmark you should quote, or advice; measured numbers are from a specific home-lab
configuration and say so. Names of prior lab systems are the author's own projects.

Source: [github.com/kenrollins/gyrus](https://github.com/kenrollins/gyrus).
