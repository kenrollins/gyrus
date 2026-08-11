# openbrain content audit — what's worth migrating

Audited 2026-08-11 against the live DB (`openbrain` on kaiju's Supabase);
protective snapshot at `kaiju:~rollik/openbrain-snapshot-2026-08-11.sql`.
Companion to the migration plan in `docs/SHADESMAR-HANDOFF.md` (Step 5).

## Headline

502 rows (357 live), 2026-03 → 2026-08, activity cratering after May (120/
183/176/11/1/11 by month — Hermes arrived in May and openbrain was
effectively abandoned, except nobody told the config). **Ken's hypothesis is
confirmed: no discernment was applied.** `confidence` is a constant 0.80
across every row; `importance` clusters at the 0.6 default-adjacent band;
`memory_links` and `open_loops` — the two patterns gyrus harvested from
openbrain's design — have **zero rows each**. The system captured; it never
judged. (This is the gyrus thesis stated as an autopsy.)

## By source (live rows)

| Source | Live | Verdict | Why |
|---|---|---|---|
| `email-signal` | 206 | **skip** (archive at most) | AI-newsletter clippings (Import AI, The Neuron, Exponential View). News, not memory-about-Ken; value time-decayed; 4-5 months stale |
| `bootstrap` | 63 | **selective extract** | Chunked markdown: some durable gold (Operating Lens, Bond Milestones — genuine preference/relationship facts), much stale ops-doc fragments (skills lists, postmortem sections) |
| `pip` | 51 | **extract, don't import** | Activity log, not facts ("Morning brief sent...", "Sent recovery advisory..."). Durable facts hide *inside* them (Knoxville, Whoop, routines) — run through extraction, drop the event records |
| `chat` + `user_input` | 26 | **MIGRATE — highest value** | Actual Ken facts and preferences, well-formed ("Ken wants the Obsidian KB curated by Pip", "Ken's quantum focus is hybrid quantum-classical + Dell Federal relevance, not deep math") |
| `conference-harvest-2026-08-07` | 8 | migrate | Recent, deliberate captures |
| `human-curated` | 1 (11 deleted) | skip | Mislabeled — actually sysadmin drift digests; already 11/12 deleted |
| `operator` + `*test*` | ~100 | **discard** | Test sentinels ("sentinel content with token unique-search-token-...") and integration-test rows |
| misc (morning-brief, task-completion, pip-initiative) | 4 | extract | Same treatment as `pip` |

Net: **~100 rows carry real value, and most of those want extraction, not
verbatim import.** The embeddings-migrate-verbatim convenience (same model +
dimension, ADR-0005) applies only to rows kept as-is — mainly the chat/
user_input set.

## Migration consequences (feeds the M1/M4 importers)

1. **Route keepers through gyrus's own extraction pass** (facts-not-
   transcripts), not a bulk INSERT. Verbatim import would reproduce
   openbrain's no-discernment corpus inside the system built to avoid it.
2. Target tiers: chat/user_input → preference + factual; bootstrap keepers →
   preference/factual; pip-activity extracts → factual; entities (431 rows)
   → M4 entity tables after re-resolution.
3. `email-signal` is a *reference corpus* question (RAGFlow-class, out of
   scope per PLAN) — not a memory-migration question. Archive the snapshot;
   don't import.
4. Cold-start expectation: ~100 quality seeds, not 500. Set the M2 decay/
   salience baselines accordingly.
