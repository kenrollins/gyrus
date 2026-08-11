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

## FINAL VERDICT (2026-08-11, second pass): skip the migration entirely

The first-pass "~100 keepers" recommendation did not survive a comparison
against Hermes's own distilled memory. `~/.hermes/memories/MEMORY.md` (34
lines) and `USER.md` (24 lines) already carry **current, better-distilled
versions of exactly the facts openbrain's best rows hold** — Obsidian
curation preference, Whoop/health, Knoxville, Dell Federal framing,
communication prefs. A row-by-row export of the 26 chat/user_input keepers
(`docs/shadesmar-notes/openbrain-keepers-review.md`, for a 10-minute human
skim) shows the remainder is historical one-offs ("traveled to GTC 2026")
and instructions about *retired mechanics* (`PIP_INBOUND_JSON`, the
pre-Hermes email pipeline). A time capsule, not living memory.

**Decision: no openbrain importers get built.** The plan is instead:

1. **One-time extraction scan over Hermes's own signals** — `state.db`
   (158 sessions, 10,467 messages, FTS-indexed, May→now, full turns) run
   through gyrus's M1 extraction pass as a backfill; MEMORY.md/USER.md
   imported as seed facts (they are already extracted — that work is done).
2. openbrain: **write-freeze** (remove the `mcp_servers` entry from Pip's
   config), stop the orphan process on kaiju:7778, keep the snapshot
   (`kaiju:~rollik/openbrain-snapshot-2026-08-11.sql`) as insurance,
   archive the DB. If the human skim of the keepers file surfaces anything
   MEMORY.md lacks, add it there by hand — a 10-minute job, not an importer.
3. `email-signal` rows remain a RAGFlow-class reference-corpus question,
   out of scope per PLAN.
4. Cold-start corpus: MEMORY.md/USER.md seeds + the state.db backfill.
   Set M2 decay/salience baselines against that, not openbrain counts.
