# ADR-0002: Tier memory by signal source, not by content type

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** Ken

## Context

gemma-forge's crown jewel is outcome-driven credit assignment: a memory's score
reflects whether following it *caused* a good outcome, validated against STIG's
hard pass/fail. The obvious worry: a personal agent has no STIG scanner, so the
crown jewel seems not to transfer — "learning about Ken" has no ground truth.

That worry is too broad. Much of what flows through Pip is not preference at all
— it is technical: a command that worked, an API quirk, a config that fixed a
thing. And because Pip is **agentic**, that slice *does* have ground truth: Pip
reuses a remembered approach, runs the tool, and gets pass/fail back. That is a
STIG signal in disguise.

## Decision

**Partition memory into three tiers by reward-signal source, and score each with
its own evaluator:**

1. **Procedural** (commands, configs, tool quirks) — TRUE ground truth via
   agentic reuse → run → pass/fail. gemma-forge's credit assignment and causal
   attribution port **1:1** here. This is the proof tier.
2. **Factual** (project facts, entities) — no hard pass/fail; scored by
   contradiction detection + corroboration frequency.
3. **Preference** (how Ken works) — proxy only: corrected? reused?
   uncontradicted? The weakest signal; never dressed up as stronger.

Transfer the machinery unchanged; **swap the evaluator per tier.** A tool's
pass/fail is the procedural tier's "shadow book" — the deterministic proxy that
signal-forge already proved out in a non-STIG domain.

## Consequences

- The port's hardest question is answered: the crown jewel survives on the
  procedural tier, which is also the tier most useful to an agent doing work.
- Scoring code must carry a tier discriminator; the dream pass runs the right
  evaluator per tier rather than one global rule.
- The falsifiable claim (BRIEF) is measured on the procedural tier: does Pip's
  tool-success-on-recall climb over sessions? If yes, the thesis holds.
- Honesty guardrail: a preference must never be scored as if it had procedural
  ground truth. Confidently-wrong preference memories are the failure mode.
