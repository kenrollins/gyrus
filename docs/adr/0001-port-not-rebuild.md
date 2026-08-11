# ADR-0001: Port gemma-forge's memory engine; don't rebuild or adopt off-the-shelf

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** Ken

## Context

Pip needs a memory layer with real hygiene — decay, salience, contradiction
handling, and outcome-driven credit assignment — not just capture and recall.
Three roads: adopt an off-the-shelf layer (Mem0 / OpenBrain / SuperMemory),
build a fresh engine, or port what already exists.

gemma-forge already contains a **measured** implementation: a 927-line dream
pass with graded salience and per-retrieval causal attribution, which drove STIG
remediation 20%→90% and 20h→4h. Its own ADRs (0016 memory stack, 0019 context-
graph attribution) document the design. Critically, the credit-assignment code
was **already generalized off STIG** (commit H-01/F-12): `skill` is a parameter
and the credit math reads outcome from a `tip_retrievals` table rather than
calling the OSCAP scanner. signal-forge has already ported the same engine once,
to investment theses.

## Decision

**Port gemma-forge's memory engine into gyrus.** Do not adopt an off-the-shelf
layer as the substrate, and do not rebuild from scratch. The dream pass, eviction,
and the Graphiti/Postgres substrate port as-is; retrieval and tip-writing adapt;
the turn-extraction parser and the per-tier outcome-signal writer are replaced
(module-lift map in `docs/design/ARCHITECTURE.md` §6).

## Consequences

- We inherit a proven result instead of re-deriving it. The single largest risk
  (does outcome-driven consolidation actually work) is already retired for the
  procedural tier.
- We take a dependency on gemma-forge's schema shape; the port must keep the
  signal-production / signal-consumption separation intact.
- Off-the-shelf layers are not wasted: **OpenBrain's design patterns are
  harvested** (open_loops, entity/link tables, the MCP adapter spec) even though
  its system is retired.
- gyrus's distinctive contribution is not the memory primitives (adopted from
  the frontier) — it is outcome-driven consolidation applied to a *personal*
  agent, via signal-tiering (ADR-0002).
