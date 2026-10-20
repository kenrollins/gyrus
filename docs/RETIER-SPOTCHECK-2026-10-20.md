# Re-tier spot check — prompt v1.5, 2026-10-20

40 live personal memories written under `lab/extract:v1.5` since 2026-10-06,
random sample, graded by Claude (Ken reviews soft calls only). Grades:
**OK** right tier and durable · **TIER** wrong tier · **DROP** not a memory
(transient, fragment, or a record a system already holds) · **soft** = Ken's call.

| id | tier | grade | note |
|---|---|---|---|
| 24100 | factual | OK | durable health correlation |
| 23113 | factual | OK | version fact; will be superseded by 23116 (reconciler should catch) |
| 23255 | factual | OK | |
| 24114 | factual | OK (dup) | same claim as 24103; cross-provenance dup below band |
| 24098 | factual | DROP | "the medication record is untouched" — transient state |
| 23492 | open_loop | OK | |
| 23268 | procedural | OK | |
| 23107 | factual | DROP | "Ken updated the animation" — fragment, no referent |
| 23478 | factual | OK | vague but true |
| 24110 | factual | DROP | "since Oct 12 only two logged drinking nights" — record state, decays in days |
| 23274 | factual | OK | |
| 23494 | factual | TIER → procedural? soft | capability limit; procedural reads better |
| 24104 | factual | OK (dup-ish) | overlaps 24102; fold candidate |
| 23288 | factual | OK | |
| 23493 | open_loop | OK | |
| 23116 | factual | OK | |
| 24107 | factual | OK | |
| 23293 | factual | OK | |
| 23789 | open_loop | OK | |
| 23688 | open_loop | DROP | "clarify what Ken meant by 'ruled'" — conversational fragment |
| 23262 | open_loop | OK | |
| 23295 | factual | OK | |
| 23278 | factual | OK | |
| 23456 | factual | DROP | "Zulip was reconnecting cleanly again" — transient status |
| 24885 | open_loop | DROP | "find the current temperature in the office" — one-shot request |
| 23687 | factual | DROP | "office lights are on" — transient state |
| 23796 | open_loop | DROP | "clarify which little sound confused something" — fragment |
| 23783 | preference | OK | |
| 23276 | preference | OK | |
| 24875 | factual | DROP | location state (gated since today; this one predates the gate) |
| 23787 | factual | TIER → procedural (bug) soft | fine either way; dup of 23792 |
| 23455 | open_loop | OK | |
| 23250 | factual | OK | overlaps 23293; fold candidate |
| 23267 | procedural | OK (dup) | same as 23268 |
| 23785 | factual | DROP | per-night alcohol clearance estimate — record-shaped |
| 23904 | procedural | OK | |
| 24097 | procedural | OK | |
| 23906 | open_loop | OK | |
| 23487 | procedural | OK | |
| 23286 | preference | OK | |

**Tally:** OK 28 (70%), of which 5 are duplicates of another live memory;
DROP 10 (25%); TIER 2 (5%, both soft).

**Reading.** Tier assignment itself is fine under v1.5 — 95% right, and the
two misses are arguable. The real leak is **durability**, not tier: a quarter
of the sample is transient state ("office lights are on", "Zulip reconnecting
again", "the record is untouched") or a conversational fragment ("clarify
what Ken meant by 'ruled'"). Three of the ten DROPs are already caught by
today's gates (location, health records); the rest share a shape — a status
sentence in present tense with no subject that outlasts the hour, or a
request/clarification with no durable referent.

**Action (shipped same day):** a deterministic durability gate in `_clean` for
the two shapes above — present-tense device/connection status ("lights are
on", "is reconnecting", "is untouched") and clarification fragments
("clarify what/which … meant") — plus the ten DROPs retired. Prompt v1.6 is
NOT opened: a prompt change needs a golden pass (ADR-0012) and the gate is
measurable without one. Duplicate pressure (5/40) is the reconciler's job; it
now runs across tiers nightly.
