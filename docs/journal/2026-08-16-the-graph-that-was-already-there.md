---
id: journal-030-the-graph-that-was-already-there
type: journal
title: "The graph that was already there"
date: 2026-08-16
visibility: public
tags: [adr-0013, reflective-tier, neo4j, graph, retrieval, claude-lane]
related:
  - adr/0013-reflective-tier-as-projection
  - adr/0001-port-not-rebuild
one_line: "The reflective tier shipped as a projection of what the store already knew — 13,249 nodes, 908 supersession chains, and an entity-relatedness write-back that lets 'NERSC' recall memories that only say 'QCAN' — after discovering that the Graphiti we planned to port was never actually used by its donor."
principle: "Before porting a dependency, grep for its imports — a declared library with zero call sites is an aspiration wearing a version pin."
---

The last unbuilt piece of the original architecture was "Neo4j + Graphiti,
PORT AS-IS from gemma-forge." Recon before building found the audit arc's
favorite shape one more time: gemma-forge *declares* graphiti-core in its
pyproject and imports it nowhere. The port-as-is label pointed at an
aspiration. The 2026-08-11 source verification had even flagged it
("Neo4j/Graphiti can be deferred") — the label just never got corrected.
And Graphiti's actual value — LLM extraction of entities and episodes — is
work gyrus has already done by the time a memory exists.

So ADR-0013 reshaped the tier: **the graph is a projection of what the
store already knows, plus derivations only a graph can compute, and the
hot path never touches it.**

## What went in

Direct driver, gyrus-prefixed labels (the `.224` instance carries another
pipeline's scaffolded-but-empty taxonomy — coexist, don't squat). Nightly
in the dream sweeper, incremental by updated_at watermark, MERGE-idempotent,
rebuildable from Postgres at any time. Neo4j down = stale projection,
loudly logged, recall untouched.

- 13,249 GMemory nodes — retired memories INCLUDED, because the graph is
  where bi-temporal history becomes traversable instead of filtered away.
- 28,309 MENTIONS edges to GEntity nodes.
- **908 SUPERSEDED_BY edges** — every reconciler fold, contradiction, and
  loop-resolution from the audit arc, now walkable. The longest chain runs
  three generations deep: "why does gyrus believe X" finally has a
  path-shaped answer.

## The part recall actually feels

Co-occurrence is computed in the graph and written BACK to a small Postgres
table; the retrieval graph-leg expands query entities one hop at half
weight, purely in Postgres. First enrichment: 4,708 relation rows, and the
spot-check sells it — `nersc` relates to `qcan`, `hamlib`, `katherine
klymko`: a "NERSC" query can now surface the QCAN program memories that
never contain the string NERSC. The graph leg stopped being a keyword
matcher wearing a fancy name.

## Casualty report, honestly

The claude-lane drain was mid-flight inside the container when the
reflective-tier rebuild restarted it — exit 137, my kill, the /tmp lesson's
sibling learned the expensive way twice in one arc: **never rebuild while
an exec job runs in the target.** The drain's own design absorbed the hit
(cursor held, dedupe eats re-extraction) and it resumed cleanly. The
claude lane itself went live upstream today — first 100 items pushed, and
the lane's first delivered insight was the thalamus session correcting MY
hostname error in the design doc. The lane works; it worked on its own
builders first.
