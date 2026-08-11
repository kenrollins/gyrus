# gyrus — the brief

## What it is

The memory system Pip (Ken's Hermes agent) uses to get smarter about Ken, his
lab, and the work — over time, from the ordinary stream of conversation and
tool use. One tiered store, two faces (a Hermes `MemoryProvider` and an MCP
server), and an offline consolidation pass that decides what survives.

## The claim it proves (falsifiable)

> Outcome-driven memory consolidation — proven on STIG's ground truth in
> gemma-forge — transfers to a *personal* agent by tiering memories on their
> signal source. Where a memory has a hard outcome (a command that worked),
> the machinery ports untouched; where it doesn't (a preference), an honest
> proxy replaces it. The result learns what to keep instead of drowning in
> what merely recurred.

**How you'd falsify it:** point Pip's memory at gyrus, let it run, and measure
the *procedural* tier — does Pip's tool-success-on-recall improve over sessions
the way gemma-forge's STIG remediation climbed 20%→90%? If procedural memories
demonstrably raise success and cut retries, the transfer holds. If they don't,
the thesis is wrong and we learn exactly where.

## Why this shape

Three things forced it, each documented as an ADR:

1. **Port, don't rebuild (ADR-0001).** Ken already built and *measured* the hard
   part — outcome-driven credit assignment with per-retrieval causal attribution
   — in gemma-forge. Rebuilding it from scratch (or adopting a thinner
   off-the-shelf layer) throws away a proven result. gyrus ports it; the code
   was already de-STIG'd, so the credit engine lifts nearly as-is.

2. **Tier by signal source (ADR-0002).** The naive move is "apply the dream pass
   to everything," which fails because a preference has no pass/fail. The insight:
   Pip is *agentic*, so a whole tier of memory — procedural (commands, configs,
   tool quirks) — *does* have ground truth (reuse → run → pass/fail). That tier
   ports gemma-forge 1:1. Factual memories lean on contradiction/corroboration;
   preferences lean on proxy (corrected? reused? uncontradicted?). Transfer the
   machinery, swap the evaluator per tier.

3. **Provider + MCP, one store (ADR-0003).** Hermes has a real `MemoryProvider`
   ABC; that's the always-injected face. The same store also wears an MCP face
   so Claude and OpenAI can drink from the same brain later. Build once.

## Alternatives rejected

- **Off-the-shelf memory (Mem0 / OpenBrain / SuperMemory).** Good at capture and
  recall; thin on decay, contradiction, salience, and any notion of *earned*
  memory. They'd throw away gemma-forge's measured advantage. OpenBrain's
  *design patterns* are harvested (open_loops, entity graph, MCP adapter); the
  system is retired.
- **Build a fresh memory engine.** Reinventing what's proven. No.
- **One model for everything / vector-only recall.** Vector similarity collapses
  on superficially-similar technical strings (gemma-forge's own retrieval
  docstring documents this failure). Hybrid retrieval is non-negotiable.
- **OpenBrain as the substrate with our logic bolted on.** Its schema is
  vector-centric with no clean home for procedural memory or salience scores;
  it would fight the port. Harvest the patterns, not the plumbing.

## The first demoable milestone

Not the whole cascade — the thinnest slice that proves life: gyrus stands up as
a `MemoryProvider`, Pip (from shadesmar, over LAN→DMZ) captures turns into the
episodic store and gets a recall injected before the next turn. Consolidation
and the procedural-tier signal come next. See `PLAN.md`.

## Who it's for

Ken, first and only — this is Pip's memory, tested from shadesmar before Pip
migrates into the lab (Hermes integration Phase 3). If it earns it, the MCP
face later makes every other agent smarter about Ken too.
