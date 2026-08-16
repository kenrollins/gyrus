---
id: journal-024-the-job-that-announced-itself
type: journal
title: "The job that announced itself"
date: 2026-08-16
visibility: public
tags: [adr-0011, event-time, prompt-v1.3, cron, tier-boundary, thalamus]
related:
  - adr/0011-event-time-grounding
  - adr/0010-extraction-stays-on-the-70b
one_line: "ADR-0011 landed (6,763 facts got real event dates — some 'fresh' knowledge turned out to be from May 2024) and prompt v1.3 fixed cron suppression by noticing that automated output usually says it is automated; where the model wouldn't comply (expires), code infers it deterministically."
principle: "When a prompt rule keeps failing, look for the signal already present in the input before writing a better plea — the cron windows had been announcing themselves all along."
---

Ken accepted ADR-0011 and asked for the deferred prompt pass, which meant one
golden-set validation gating three changes: event-time grounding, the
knowledge/factual boundary, and cron suppression.

## Event time: the store finds out how old it really is

Migration 0007 added `event_at` and `valid_until`; ingest now keeps the
source item's `published_at` instead of discarding it; the knowledge
evaluator decays on `coalesce(event_at, created_at)`; the dream pass retires
expired rows before scoring. The backfill (read-only paging over the
thalamus items, verified faithful upstream yesterday) stamped **6,763
facts** — every sourced email, github, and arXiv memory, 100% coverage.

The first sanity query told the whole story: 223 facts from the zettlekasten
repo carry event dates of **May 2024**. Two-year-old documentation had been
scoring as this week's knowledge since the moment it was ingested, because
`created_at` measures the ingest job. It now decays as what it is. The
conversation-extracted tiers keep NULL `event_at` — the original Hermes
capture stored only role and content, so their true times are unrecoverable,
and NULL (= created_at behaviour) is the honest default rather than a
fabricated date.

## Cron: the tell was in the window the whole time

v1.2's automated-output rule failed the goldens (6 and 4 facts where the
right answer is 0), and the first v1.3 iteration — describing automated
output's *shape* — still failed. Reading the failures showed why: one
extracted "fact" was literally *"the system is designed to automatically
deliver the final response when running as a scheduled cron job."* The model
had read the window telling it this was a cron job, extracted that sentence
as a memory, and kept going.

The fix was not a better plea; it was naming the signal: **automated output
usually announces itself.** Any mention that the run is scheduled, and any
"user" message that is a pasted skill/command file rather than something a
person typed — each tell alone means return `[]`. Both cron goldens now
return zero. And because a prompt is persuasion, not enforcement, the same
day added the missing lock: `/v1/extract-window` now 422s on cron-platform
turns — the worker and the backfill already filtered, so this closes the
last unlocked door with a deterministic guard in front of the prompt rule.

## The boundary holds; the model's compliance has limits

The "would it still be true if Ken never existed" test, extended to cover
Ken transcribing his own conference notes, moved non-cron wrong-tier from
~20% to ~0–3% on the goldens — Azure's Resource Estimator, DARPA's programs,
and the arXiv papers all file as `knowledge|relayed` now. The re-tier sweep
drops from recurring chore to occasional check.

The `expires` field is the honest failure: the model ignored it even with a
verbatim example in the prompt. Rather than a third round of persuasion,
`_clean()` infers expiry from the fact's own words ("by Monday" → week), on
open_loop and preference only — the tiers where frozen ephemera do damage.
Deterministic beats persuasive, three times in one day.

## A question from upstream found a hole down here

Mid-pass, the thalamus session asked whether its content-hash change (edited
docs re-crossing as new items) would be absorbed cleanly. Checking the
answer exposed a real gap: the exact-hash conflict path bumped corroboration
with **no same-source guard** — migration 0006 fixed the cosine path and
missed this one. A weekly-edited doc would have self-corroborated its
unchanged paragraphs, the 29× newsletter defect through the other door.
Patched: same-source exact matches are silent no-ops, cross-source still
corroborates. The boundary keeps earning its keep — two sessions, one
contract, and the question itself was the audit.
