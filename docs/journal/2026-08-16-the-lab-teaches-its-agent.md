---
id: journal-031-the-lab-teaches-its-agent
type: journal
title: "The lab teaches its agent"
date: 2026-08-16
visibility: public
tags: [claude-lane, m5, echo-guard, provenance, mcp, verification]
related:
  - adr/0009-email-edge-collector
  - adr/0002-tier-by-signal-source
one_line: "The claude lane landed end to end — 884 pre-distilled insights from ten projects' Claude sessions, honestly event-dated back to February — with the echo-chamber guard installed before MCP read-access could create the loop it prevents, and an 83% provenance over-attribution caught and clamped on the first drain."
principle: "When agents become sources, independence needs a mechanism: a reader that restates is not a witness, and a secondhand record of the owner speaking is not the owner speaking."
---

Ken's instinct — "we have Claude instances spread throughout the lab;
should we probe their files for learned insights?" — became a working lane
in under a day, and its verification produced two design corrections that
generalize to any system where agents feed agents.

## The lane

The third use of the edge-pusher pattern: daily crons on xr7620 and
shadesmar walk `~/.claude/projects/*/memory/` and repo CLAUDE.md files into
thalamus; gyrus pulls them as trusted. Verified end to end: **884 facts
from ten projects**, 100% knowledge tier, 100% event-dated by file mtime —
840 of them genuinely backdated, so February's operator-project lessons
score as February, not as this week's news. Corroboration flat at 1.00.
The content is the genre this store's best memories already were: "vLLM
0.24 loads as modelopt_mixed with image 26.07-py3", orchestration
decisions, migration records.

The drain itself was a stress test nobody scheduled: killed once by a
container rebuild (exit 137, my own — the rebuild-during-exec lesson,
twice now), stopped twice by a gateway restart and a kaiju starved by
Pip's own evidence-gathering — and every stop held its cursor and resumed
clean. The zero-shaped-failure work of the audit is what made a chaotic
deployment day boring in the good way.

## Correction one: the echo guard, installed before the echo exists

The moment sessions get MCP read-access to this store, a loop opens: a
session reads fact X, restates it in its memory file, the lane re-ingests
it under a new source_key, and cross-source corroboration fires — a
repeater dressed as an independent witness, gaining authority per round
trip. The 29× newsletter footer, in a trench coat.

The guard is deterministic and was deployed BEFORE any session got a
token: the claude lane never corroborates, on either dedupe path. Novel
insights enter at full value; restatements fold silently; authority can
only come from non-claude witnesses. Sequencing was the point — today's
memory files are still genuinely independent, so the guard closes a door
nothing has walked through yet.

## Correction two: secondhand Ken is not Ken

83% of the first drain arrived `ken_said` — sessions faithfully record
"Ken approved X", and the extractor believed them. But ken_said carries an
authority bonus, and the claude lane is structurally secondhand: a
session's contemporaneous record of Ken is a good witness report — which
is exactly what `relayed` means. Clamped at ingest, 731 facts backfixed.
ADR-0002's oldest guardrail, applied to a source that didn't exist when it
was written: never dress a weaker signal as a stronger one.

## What the lane surfaced on day one

Its first delivered insight corrected its own design doc (the thalamus
session catching my hostname error). Its first drain surfaced a fact from
a project this whole build never touched — a `nemoclaw` session recording
an agent topology ("sibling agent Pip runs on crawdad, intentionally
unknown to Nix") that reads like either stale history or a corner of the
lab this store has never seen. Both are the lane working: cross-project
knowledge moving to where it can be recalled, corrected, and — now —
explained.
