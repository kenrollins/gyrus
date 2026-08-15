---
id: journal-018-the-newsletter-that-corroborated-itself
type: journal
title: "The newsletter that corroborated itself"
date: 2026-08-15
visibility: public
tags: [m2, m5, consolidation, corroboration, email, dream-pass]
related:
  - adr/0002-tier-by-signal-source
  - adr/0009-email-edge-collector
one_line: "Pre-commit review of the first full-corpus consolidation caught a legal footer at 29x corroboration — one newsletter restating itself every issue — which forced corroboration to learn the difference between repetition and independence, and the tier firewall had already contained the damage before anyone noticed."
principle: "A corroboration signal is only as good as the independence of its witnesses; count sources, not restatements."
---

The plan for the evening was ceremonial: run the dream pass over the newly
loaded corpus — now ~12,900 memories after the github and email backfills —
review the dry run, and commit. (The commit stamps say a smaller committed run
already happened on 2026-08-13, over the ~4.1k-memory store of that era; this
one is the first over the full multi-source corpus, at 3x that size.) The
pre-commit check that was supposed to showcase cross-newsletter corroboration
instead produced this leaderboard:

- 29x — "AlphaSignal is based in the United States, with a privacy policy
  governed by U.S. laws."
- 10x — the recurring author-bio of a newsletter contributor.
- 7x — the same bio, phrased slightly differently.

The most corroborated "knowledge" in the store was a legal footer.

## Repetition is not testimony

The mechanism was working exactly as built. Write-time dedup folds a
near-duplicate fact (cosine ≥ 0.93) into the existing memory and bumps its
corroboration count — because under ADR-0002, a fact restated in different
words is evidence. That assumption was calibrated on conversations, where a
thing said twice usually means two occasions to mean it.

Newsletters break the assumption structurally. Every issue of AlphaSignal
carries the same footer, the same bios, the same sponsor scaffolding. The v1.2
extraction rule suppressed almost all of it (10 boilerplate facts survived
from 311 issues — ~0.5%), but the few survivors each arrived dozens of times,
and every arrival was one source talking to itself. Corroboration, as ADR-0002
means it, is *independent* restatement. The counter couldn't tell witnesses
from echoes.

Two details made this a good failure instead of a bad one. First, the tier
firewall had already contained it: email facts land in the knowledge tier, and
the knowledge evaluator scores on recency × demand, deliberately ignoring
corroboration (a knowledge item has no corroboration loop to earn from). The
polluted counters never moved a single utility score. The tier-by-signal-source
design defended a flank nobody was watching. Second, the genuine signal showed
up right beside the pollution: 45 facts at 2x, most of them the same story
covered by two different newsletters — the cross-source overlap the email lane
was supposed to produce.

## The fix: name the witness

Memories now carry a `source_key` — the canonical origin, at the granularity
where independence lives: the newsletter (not the issue), the repo (not the
file), the paper. When persist() finds a near-duplicate and both sides share a
source_key, the duplicate is dropped without a bump. Cross-source duplicates
still corroborate. The conversation path passes no key and keeps its original
behaviour, which is honest: we cannot yet distinguish Ken restating a fact
from Ken echoing himself, and pretending otherwise would be a different lie.
All 8,100 sourced memories were backfilled with keys; the ten surviving
boilerplate facts were retired.

## The first full-corpus commit

With the counters honest, the ceremony proceeded. Dry run over 12,889
memories: confidence up on 327, down on 24, three near-duplicate merges (the
0.97 backstop behind the 0.93 write-time gate), and zero evictions — not
because nothing is evictable but because nothing in a four-day-old store has
had the 21 days of fair chance the eviction guard demands. The top of the
utility ranking was Ken's Dell Federal quantum strategy, the NERSC Doudna
system, vault paths, speaker attributions; the bottom was activity-log
procedurals from a retired pipeline, sitting at 0.398 and aging toward
eviction. The sort is doing what the thesis needs it to do — signal from
noise, on real data, with the commit flag on this time.

One measured caveat for the next scale-up: the exact near-duplicate scan is
O(n²) and took 7m36s at 12,889 memories (2026-08-15, in-container). Fine
offline at this size; it will not survive another 3x without bounding the
candidate set. Noted before it becomes a incident, which is the whole point of
reviewing dry runs.
