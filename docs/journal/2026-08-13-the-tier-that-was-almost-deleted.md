---
id: journal-014-the-tier-that-was-almost-deleted
type: journal
title: "The tier that was almost deleted"
date: 2026-08-13
visibility: public
tags: [m4, knowledge-tier, adr-0006, reclassification]
related:
  - adr/0006-knowledge-tier-and-source-ingestion
  - docs/fable-review/04-handoff-queue
one_line: "The 709 memories the review flagged as noise-to-scope-out turned out to be a first-class tier once we saw them right — curated world-knowledge, not clutter — so M4 reclassified them into a knowledge tier with its own evaluator and a surface to browse them, rather than deleting them."
principle: "Before you delete the thing that doesn't fit, check whether it doesn't fit because it's noise, or because it needs a home you haven't built. The review called it bloat; it was a missing tier."
---

The Fable review's F4 was blunt: ~27% of the store was domain knowledge, not
memory about Ken, and its recommendation leaned toward scoping it out. Ken's
correction was sharper: that content is the *product* of three days of
deliberate conference note-taking and the whole point of pointing the agent at
high-signal sources. It wasn't noise. It was a tier without a home.

M4 built the home. A `knowledge` tier (ADR-0006) — a fourth signal class in
ADR-0002's terms: no outcome, no corroboration loop, scored instead by source
authority x recency x retrieval-demand. It sits in the same store, retrieved
through the same hybrid ranker but **down-weighted**, so a fact about Ken always
outranks a fact about the world when both match. And a `/v1/insights` surface to
*browse* what's being gleaned, by source and topic — because the highest-value
use of this tier is Ken reading it, which is why browsing it counts as demand
(ADR-0008), the same signal that will later promote a paper to deep storage.

The reclassification is the part worth remembering. 709 memories the review
would have discarded were instead *moved* — factual, non-personal, unanchored —
into the knowledge tier, their source inferred from content (industry 536,
arXiv 87, podcast 47, conference 39). Nothing deleted. The extractor that filed
them as "factual/assistant_suggested" wasn't wrong to keep them; it just lacked
the tier to file them correctly, because the tier didn't exist yet.

What's live: the tier, the gate (the extractor now decides teaching-about-Ken
vs recording-the-world on the way in), the down-weighted retrieval, the
recency/demand evaluator in the dream pass, and the browse surface. What's next
is M5 — thalamus, the ingestion service that feeds this tier from email,
podcasts, and the arXiv lane Ken is blind to, and closes the insight leak the
OpenBrain retirement opened.

## Related

- [ADR-0006](../adr/0006-knowledge-tier-and-source-ingestion.md) — the knowledge tier
- [fable-review handoff](../fable-review/04-handoff-queue.md) — F4, now closed the right way
