---
id: journal-020-what-the-store-is-actually-worth
type: journal
title: "What the store is actually worth"
date: 2026-08-15
visibility: public
tags: [audit, store-grading, knowledge-tier, thalamus, tiers]
related:
  - adr/0002-tier-by-signal-source
  - adr/0006-knowledge-tier-and-source-ingestion
  - adr/0008-earned-value-retention
one_line: "First-ever grading of the memories themselves (153-row stratified sample): ~41% of the store is keep-grade, ~45% is noise, ~14% is filed under the wrong evaluator — and the noise is mostly scoping and time, not extraction."
principle: "Grade the artifact, not the pipeline. Every pipeline metric is a proxy for the store, and the store can be graded directly."
---

Four days of building produced 12,886 memories, and every model decision along
the way — lane bake-offs, prompt lineage, union passes — was a proxy for one
unasked question: are the memories any good? Nobody had read one and said keep
or drop. This session did, for 153 of them: a seeded stratified sample
(`setseed(0.42)`) across tier × source, each graded keep / drop / wrong-tier.

| stratum | n | keep | wrong-tier | drop |
|---|---|---|---|---|
| github | 30 | 37% | 7% | 57% |
| email | 25 | 60% | 0% | 40% |
| industry | 12 | 50% | 17% | 33% |
| arxiv | 12 | 83% | 0% | 17% |
| knowledge/conversation | 8 | 100% | 0% | 0% |
| podcast | 6 | 33% | 33% | 33% |
| conference | 6 | 50% | 0% | 50% |
| factual | 20 | 5% | 60% | 35% |
| procedural | 12 | 58% | 25% | 17% |
| preference | 12 | 50% | 8% | 42% |
| open_loop | 10 | 60% | 0% | 40% |

Store-weighted: **~41% keep, ~45% drop, ~14% wrong-tier.** The weighting
matters because the worst large source (github) is half the store and the best
sources are the smallest.

## The noise is not what the pipeline metrics were watching

The lane benchmarks asked whether extraction was faithful. It mostly is — the
drops are upstream and downstream of the model:

**Scoping.** The github lane ingested Ken's own repos wholesale, and 26% of its
facts (1,639 of 6,344, measured by path) come from `docs/archive/`,
`historical/`, or vendored framework files. An archived status doc's
"environment setup needed for next session" became an eternal fact; a vendored
framework's command boilerplate was stored with `provenance: ken_said`,
inheriting Ken's authority. The extractor did its job faithfully on inputs
that should never have reached it.

**Time.** Facts carry `created_at` (extraction time) but no event time. A
March newsletter ingested in August is indistinguishable from today's news; "Ken
wants to avoid processing email tonight" outlived the night as a durable
preference. Ephemera freeze into eternity because nothing in the schema lets
them expire.

**Tier drift.** The factual tier — supposedly personal project facts, scored
by corroboration — is ~60% relayed world knowledge (conference talks, vendor
specs), because those rows were extracted on 08-12/08-13, *before* the
knowledge tier existed (migration 0004), and were never re-tiered. ADR-0002's
whole thesis is matching evaluator to signal source; today the corroboration
evaluator is scoring a majority population it was never designed for. The
pre-ADR-0006 backlog needs a re-tiering sweep more than any prompt needs tuning.

**Provenance inflation.** The subtlest defect and the most dangerous for an
agent that acts on Ken's behalf: arrival keeps getting promoted to intent.
A paper landing in a category firehose became "Ken is tracking research on X";
an assistant suggestion became a preference; one of several *competing* design
documents became a decided fact. Each is a small lie about who said what,
stored at the same confidence as truth.

## Does the knowledge tier earn its place?

Ken's framing (brief §8): not "is 72/28 the right ratio" but "does the tier
earn its keep". Verdict: **provisionally yes — as a tier; not yet as currently
populated.** arXiv grades 83% keep, conversation-knowledge 100%, email 60%
with real cross-source value; the retrieval path already down-weights
knowledge at 0.6 and the insights surface logs browse-demand, so ADR-0008's
machinery is in place. Demand data (7 recalls against 6,344 github rows) looks
damning but is confounded: retrieval logs span three days and most of the tier
arrived in the last two. The tier that cannot currently justify itself is
github-as-ingested — half the store, graded worst, from one day's ungated
ingest. The earned-value gate ADR-0008 already prescribes for the firehose
should apply to the trusted path too: re-scope it (current docs only, no
archives, no vendored files), and let the rest earn re-entry through demand.

The dream pass's demand/recency decay will eventually evict what this grading
calls noise — but eviction guards want 21 days of fair chance, and the
procedural thesis (M3/M4) shouldn't wait behind a store that is half filler.
Re-scope at the source, re-tier the legacy rows, and grade again in a month:
same seed, same strata, and the delta is the honest progress metric that
memory counts never were.
