# The gyrus journal — style & contract

Third-generation journal. gemma-forge proved the build journal is the most
valuable artifact a project produces; qaoa-grid-ops proved that if the journal
isn't written *as you go*, it doesn't get written. This file merges the two
STYLE contracts and fixes their two failure modes:

- **gemma-forge overshared.** One publication tier meant candor calibrated for
  a build log shipped to the customer-facing site ("embarrassing in
  real-time", tool-procurement anecdotes, self-incriminating nav titles).
- **qaoa-grid-ops under-recorded.** The implementation journal directory was
  created and stayed empty; decisions evaporated into commit messages.

If a new entry gets written without reading this file first, the voice drifts.
That is the pain signal that tells you to re-read it.

## Layout

```
docs/journal/           chronological build journal (this is the diary)
docs/journal/gotchas/   atomic "X breaks Y because Z" — no narrative needed
docs/adr/               decisions (already exists; entries MUST link to it)
docs/design/            durable architecture, rewritten in place
```

Entry files are **date-first flat**: `YYYY-MM-DD-slug.md`. Chronology is
intrinsic, insertion is free, and no decimal-numbering pileup (gemma-forge's
`38.5`–`38.13`) can recur. Multiple entries per day are fine — the slug
disambiguates. Sequence lives only in `id:`.

## Frontmatter (required)

```yaml
id: journal-NNN-short-slug        # NNN = simple running sequence
type: journal | gotcha
title: "Punchline, not topic"     # no 'Journal:' prefix, no self-incrimination
date: YYYY-MM-DD
visibility: public | internal     # THE gemma-forge fix. Decide at write time.
tags: [m0, platform, verification]
related:
  - adr/0004-own-dmz-service      # ≥1 ADR or design doc, always
one_line: "The finding compressed to one sentence — written FIRST, not last."
principle: ""                     # optional: the generalizable claim, for deck harvest
```

`visibility: internal` keeps an entry in the repo and out of the published
site. The test for `public` (from qaoa's contract): **our own errors appear
when they teach something general — framed as the finding, not as
autobiography.** If the sentence names the author's affect ("embarrassing"),
the tooling we happened to use, or a mistake that doesn't generalize, it's
internal. Honesty is not the casualty — the *audience* is chosen per entry.

`principle:` feeds the presentation harvest: entries carrying one roll up into
deck source (principle / evidence / applicability / speaker notes — the
gemma-forge slide shape). Write it only when the entry genuinely earns a
slide.

## Voice (type: journal)

Inherited from gemma-forge, which got this right:

- **Predicament first.** Open with the situation, not the setup.
- **Punchline headers.** `## The address that answered twice`, not
  `## Network debugging`. Banned scaffolding H2s: "Why this is its own
  entry", "What we expected", "Background".
- Observational restraint; name the absurd when it is absurd; no emojis;
  no pull-quotes except when one earns it.
- **Prediction before outcome.** If you lay a bet, write it before the run.
  A prediction entry written after the outcome is a fiction.
- Numbers carry provenance (measured when? where? by what command?).

## Voice (type: gotcha, and anything public-facing)

Inherited from qaoa-grid-ops, which got THIS right:

- Atomic: one mechanism per entry, readable without the journey.
- Define terms on first use; distinguish **proved / measured / expected**.
- Claims discipline: this is shown to people who will check. Every number is
  measured or it is labeled a guess. State the boundary of what was tested.
- Corrections are first-class: wrong entries get amended in place with a
  dated note, never silently rewritten.

## Cadence

Write the entry in the same session as the work. The context that makes an
entry worth reading — what you believed before, what surprised you — is
unrecoverable a week later. An ugly same-day entry beats a polished
retrospective. Editorial passes happen later and are themselves journaled.

## Index

`docs/journal/index.md` is **generated** (`tools/build_journal_index.py`)
from frontmatter — never hand-edited. gemma-forge's phase-grouped index with
one-clause payoffs is the model; here the `one_line` field provides the
payoff, which is why it's required and written first.
