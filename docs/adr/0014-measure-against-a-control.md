# ADR-0014: Measure the thesis against a control, not against a curve

- **Status:** Accepted
- **Date:** 2026-10-20
- **Deciders:** Ken (on the 2026-10-20 review, `docs/REVIEW-2026-10-20.md`)
- **Amends:** ADR-0002 (the falsifiable claim), BRIEF.md

## Context

BRIEF.md's falsifiable claim borrowed gemma-forge's shape: Pip's
tool-success-on-recall should climb over sessions the way STIG remediation
climbed 20% → 90%. Two months of running showed why that cannot happen here,
independent of the dead-sweeper bug (journal-035):

- STIG had a 20% baseline and a hard pass/fail per rule. Pip's tools succeed
  about 97% of the time (`tools 73/75 ok` is a typical turn). A success rate
  that starts at the ceiling has no room to climb.
- Credit saturates: `followed + succeeded = +1.0`, mapped through
  `0.5 + credit`, caps at confidence 1.00 after three samples. Since
  2026-08-31 there were 86 followed procedural recalls on 16 memories and
  exactly one negative outcome. No variance, no discrimination, no curve.
- The "demand" signal the proxy tiers rest on (`recall_count`) was being
  written mostly by cron jobs (review D1), so even the proxy numbers were not
  measuring use.

"The curve needs usage" was the comfortable reading. The accurate one is that
the measurement was adopted from a domain with ground truth into one that
mostly lacks it, and ADR-0002 half-admitted this by inventing proxies for
every tier but one.

## Decision

The claim is measured two ways, neither of which needs a failing baseline:

1. **Procedural recall vs. a withheld control.** On a fixed fraction of
   eligible turns (`recall_control_every`, default 1 in 8; never cron, never
   the MCP face) gyrus computes recall as usual, logs it with
   `memory_retrievals.withheld = true`, and returns nothing to the agent.
   Every scored turn records its tool outcome (`ok`, `fail`, `retries`,
   `withheld`) in `episodic_turns.meta->'outcome'`. The claim holds if served
   turns show fewer retries and tool failures than withheld turns on work
   where a procedural memory was recalled. Retries — a tool failing and the
   same tool being called again in the turn — are the observable cost of
   missing or wrong memory, and they vary even when the final result is a
   success.
2. **Human-graded precision of personal recall.** Monthly, sample recent
   served recalls (`tools/store-audit/sample_recalls.py`), grade each
   injected memory as relevant / harmless / wrong for its query, and track
   the relevant share. The August audit did this once by hand (41% keep →
   ~70% after repair); it becomes a recurring number.

The per-memory credit assignment stays as the procedural tier's evaluator —
it is still the only earned signal — but it is no longer what proves or
disproves the project.

## Consequences

- Recall is deliberately withheld on ~12% of eligible turns. That is a real
  cost to Ken, paid to get a number; the fraction is a setting and can be
  turned off (`0`) once the comparison is significant.
- Withheld rows are never outcome-scored as followed (they were not shown)
  and never bump `recall_count`.
- Demand only counts from real readers: cron sessions and warm-up fetches do
  not log retrievals, and a memory is evictable again if not recalled within
  a window (review D2) rather than immune after one recall.
- BRIEF.md's "How you'd falsify it" paragraph is rewritten to this ADR.
  TASKS.md's "THE CURVE" item is closed as *not measurable as stated* and
  replaced by the control comparison.
