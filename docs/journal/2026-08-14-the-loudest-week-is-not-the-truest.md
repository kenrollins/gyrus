---
id: journal-016-the-loudest-week-is-not-the-truest
type: journal
title: "The loudest week is not the truest"
date: 2026-08-14
visibility: public
tags: [m5, thalamus, knowledge, retrieval, sources]
related:
  - adr/0007-thalamus-ingestion-boundary
  - adr/0006-knowledge-tier
one_line: "Ranking a user's interests by raw memory count measured how noisy each week was, not what mattered — breadth (distinct sessions) told the truth, and the real fix was a new source, not a better query."
principle: "Frequency in a memory store measures volume, not importance; correct for it by breadth, and fix the bias at the source rather than the query."
---

The ask was simple: scan gyrus, tell Ken which arXiv topics to watch. So I
counted entities across the knowledge tier and handed back a watchlist topped by
Rigetti, NERSC, ORNL, Qblox — a wall of quantum hardware. It looked like a
precise read of his interests. It was a precise read of one week.

Ken pushed back before I could congratulate myself: *"don't over-rotate on that
conference — I've got lots of AI stuff as well."* He'd spent three days at a
quantum conference with Pip taking notes as fast as the talks came. That week
alone is one of the densest sessions in the store.

## What the raw count was actually measuring

I re-ran the scan two ways. Raw mention count put Rigetti at 72. Counting
**distinct sessions** an entity appears in put Rigetti at 3 — seventy-two
mentions, all inside three sittings. One conference, echoing.

The session histogram made it undeniable: two sessions hold roughly half of all
4,109 memories. A frequency ranking over that store isn't a ranking of interest.
It's a ranking of which weeks generated the most text. The conference was loud,
not central.

By breadth, a different Ken appears — the one whose interests recur across many
separate sittings: Dell Federal, NVIDIA, HPC, his own tooling, and an AI signal
(OpenAI, ChatGPT, the AI Daily Brief) that raw counts had buried under quantum
nouns. Post-quantum cryptography spanned four sessions and my first pass had
missed it entirely, because in no single week did anyone say "PQC" seventy-two
times.

## The fix that wasn't a query

The obvious repair is to divide by volume and re-rank — and I did, rebalancing
the watchlist around breadth and the lens of Ken's actual work (federal-viable
local models, the AI-times-quantum crossover where Dell has an infrastructure
play). But de-biasing the query only launders a biased corpus. The corpus is
biased because of *how it's fed*: conversation volume is bursty by nature, and a
conference is a burst.

Ken named the structural fix himself: his GitHub project journals. He writes them
in detail, across many repos, over months. Unlike a conference, that signal is
spread across time by construction — so it corrects the volume bias at the
source instead of in the ranking. It became a new thalamus adapter (README +
`docs/` markdown, commit messages deliberately excluded as too noisy to earn the
extraction gate), sitting beside the arXiv lane behind the same source-item
contract (ADR-0007).

## The boundary of what was tested

The breadth re-scan is measured (`COUNT(DISTINCT source_session_id)` over 4,109
live memories, 2026-08-14). The rebalanced watchlist is a judgment call informed
by that scan, not a measured improvement — its proof is whether `/v1/insights`
fills with on-lane papers over the coming cycles. The GitHub lane is built and
wired but unproven until a token lets it run; whether repo journals actually
outsignal conference bursts is a prediction, not yet a result.

The generalizable part is smaller and firmer than any of that: in a memory
system, *how often* a thing was written down tells you how eventful its week
was, not how much it matters. If the consolidation engine ever scores importance
by frequency, this is the trap it will fall into — and the same correction
applies. Weight by breadth; and when a signal source is structurally bursty, fix
the source, not the score.
