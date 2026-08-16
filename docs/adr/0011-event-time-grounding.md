# ADR-0011: Memories carry event time, not just extraction time

- **Status:** Accepted (Ken, 2026-08-16)
- **Date:** 2026-08-15
- **Deciders:** Ken

Implemented 2026-08-16: migration 0007 (`event_at`, `valid_until`), ingest
sets `event_at` from the source item's `published_at`, prompt v1.3 emits
`expires` on explicitly time-scoped facts (mapped via `EXPIRES_DAYS`), the
knowledge evaluator scores recency on `coalesce(event_at, created_at)`, and
the dream pass retires expired rows before scoring. Rode the same golden-set
validation as the v1.3 cron/tier changes (journal-024).

## Context

The store grading (journal-020) found that the second-largest noise class —
after stale-path github sources — is **time**: facts whose truth is scoped to a
moment, stored as if eternal. Three concrete shapes, all measured in the
sample:

1. **Backfilled news reads as current.** The email lane ingested March–August
   newsletters in one day; every fact's `created_at` is 2026-08-15. "OpenAI
   updates Agents SDK" from March is indistinguishable from yesterday's news.
   The knowledge evaluator scores on *recency* — computed from `created_at`,
   which for backfill measures the ingest job, not the news.
2. **Session-scoped intents freeze into preferences.** "Ken wants to avoid
   processing email *tonight*" (id 47) outlived the night. The preference tier
   graded 42% drop, and most drops were this shape.
3. **Status snapshots become facts.** "Ken requires environment setup for the
   *next session*", "the *first* maintenance run pruned 67 sessions" — true
   once, stored forever, no field to say when "once" was.

The schema has `created_at` (extraction time) and nothing else. Nothing in
extraction, scoring, or retrieval can currently distinguish "true as of when
it happened" from "true now".

## Decision (proposed)

Two nullable columns on `memories`, one extraction-prompt change, one scoring
change:

1. **`event_at TIMESTAMPTZ`** — when the fact was true/observed, when known.
   Set by the extraction pass when the source carries it (email `Date:` header,
   arXiv submission date, github commit date — thalamus already normalizes
   `published_at`; the ingest path simply stops discarding it). NULL means
   "unknown, assume created_at" — today's behaviour, so the change is
   backwards-compatible and requires no backfill to ship.
2. **`valid_until TIMESTAMPTZ`** — an expiry hint for facts the extractor can
   already see are scoped ("tonight", "next session", "this week"). The dream
   pass retires (soft, as always) expired rows instead of waiting for demand
   decay to starve them over weeks. Most facts never get one; the extractor
   sets it only on explicit temporal scoping, which the grading shows it can
   see — the words are in the fact text it already wrote.
3. **Knowledge recency scores on `coalesce(event_at, created_at)`** — the one
   place the lie currently does damage: a March story backfilled in August must
   decay as March, not August.

## Consequences

- The email lane's grading defect (60% keep, with temporal ungroundedness the
  main failure) becomes fixable at the source: the `Date:` header is in the
  source item already.
- The preference tier stops accumulating expired intents; open_loop gets an
  honest staleness signal ("Ken asked X" three weeks ago is not still open).
- One more prompt change means one more golden-set pass (the cron-suppression
  lesson: prompt changes are never free). This ADR should ride the same
  bench_lanes run as the cron fix rather than triggering its own.
- Explicitly NOT in scope: bi-temporal modelling of belief revision
  (`superseded_by_id` already covers "we learned better"); this is only about
  when the world was as described.
