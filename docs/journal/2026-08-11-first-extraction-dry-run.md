---
id: journal-006-first-extraction-dry-run
type: journal
title: "The extraction pass met real conversations before it exists"
date: 2026-08-11
visibility: public
tags: [m1, extraction, evaluation, models]
related:
  - adr/0002-tier-by-signal-source
  - adr/0005-embeddings-via-gateway
one_line: "A v0 extraction prompt run against last week's real quantum-conference turns: both models scored 100% precision, but the flash model extracted zero domain facts while the 70B got the panel roster and three strategic insights — model choice dominated prompt design, and both missed the same disguised preference."
principle: "Evaluate extraction on real conversations before building it — the golden corpus already exists in the agent's own history, and it will tell you things no synthetic test can."
---

The question landed before M1 did: *will the extraction pass grab truly
relevant facts — the kind from last week's quantum conference — or something
else?* The honest answer was that extraction doesn't exist yet; M0 stores
raw turns on purpose. But the question deserved better than "wait and see",
and the means to answer it early were already lying around: the conference
conversations are sitting in the agent's own capture database as real
turns, and the gateway can run a draft prompt today.

## The setup

Golden corpus: the actual sessions from the conference week — hundreds of
Ken's own messages under titles like "Whiteboard notes for quantum
conference" and "Insights from NQISRC Directors Panel". A 22-message window
from the panel session went through a v0 extraction prompt (the ADR-0002
tier taxonomy plus discernment rules: skip pleasantries, skip one-task
formatting, skip compaction blocks, atomic self-contained facts, provenance
labels), temperature 0, two models.

The window was usefully hostile: duplicate sends, a [CONTEXT COMPACTION]
marker, ASR-garbled transcript passages. Real capture is not clean.

## The result

Precision was 100% on both models — nothing false, nothing noisy. Recall
split them wide open:

- **The flash model (35B, thinking off)** extracted four facts: two contact
  emails, a tone preference, a conference date. It skipped every piece of
  quantum domain knowledge in the window.
- **The 70B** extracted six: the full panel roster (moderator and five
  center directors, all entity-tagged) and three strategic insights — the
  centers shifting from "prove a qubit works" to "build an ecosystem that
  can do science", hybrid quantum+HPC as core with Frontier coupling,
  modularity as the practical scaling answer. Exactly the facts a field CTO
  wants his agent to remember.

Same prompt, same window, same temperature. **Model choice dominated prompt
design.** Since extraction is an offline pass where latency is cheap, the
big model earns the job — and a union-of-two-models pass is now a live
question for the bake-off.

## The shared miss

Both models missed the same memory, and it's the instructive one. Ken asked
for "the end-of-day summary formatted for Outlook — Dell Federal insights,
TL;DR at the start, like yesterday's." The v0 discernment rule *skip
formatting requests bound to this single task* ate it. But a format asked
for twice is not task logistics — it's a preference being born. Detecting
that requires recurrence awareness, which a single-window extractor cannot
have. Either the dream pass promotes repeated near-identical requests into
preferences, or extraction gets cross-session context. Noted for M1 design;
this is exactly the kind of finding the test phase exists to surface.

## Amendment, same day: scale is not the lever

The obvious follow-up — "so do we need the 120B, or bigger?" — got tested
within the hour. The 120B on the same prompt *caught* the disguised format
preference (as a procedural memory, full section list) but *lost* every
quantum domain fact the 70B had found. Scale reallocated attention; it
didn't add extraction quality. Meanwhile a one-rule prompt change
(recurrence-aware: "a format request referencing a prior instance is a
preference") took the 70B to the best result of any run — seven facts,
domain knowledge AND the format preference, still 100% precision. The 253B
couldn't be tested at all: NVIDIA had silently retired its hosted endpoint
(the day's third instance of dead wiring behind working fallbacks; the
gateway's fallback lanes were repointed to the live 550B the same hour).
Full table in `tools/extraction-eval/README.md`. Revised bet for M1: the
70B plus an iterated prompt, with union-of-models as the open question —
not a bigger model.

## What this hardens

The test harness now lives in `tools/extraction-eval/` with the dry-run
results, and M1's definition of done gained a gate: a golden set of real
windows (including cron output, which must extract approximately nothing),
graded for precision AND recall per tier against Ken's answer key. The
acceptance test is Ken keeping ≥80% of extracted facts and finding <5%
noise. The extraction pass will meet its evaluator before it meets
production — the reverse of how memory systems usually earn trust.

## Related

- [ADR-0002](../adr/0002-tier-by-signal-source.md) — the taxonomy the prompt implements
- [tools/extraction-eval](../../tools/extraction-eval/README.md) — harness + full results table
