# extraction-eval — the M1 extraction test harness (started pre-M1)

Ken's requirement (2026-08-11): before the extraction pass ships, prove on
REAL conversations that it grabs truly relevant facts — the quantum-conference
sessions from 2026-08-03→06 are the golden corpus (they're in Hermes
`state.db`, sessions titled "Whiteboard notes for quantum conference",
"Conference note cleanup support", "Day 3 Dell Federal Summaries",
"Insights from NQISRC Directors Panel").

## Workflow

1. `dump_window_shadesmar.py` — runs ON shadesmar via
   `ssh agent@shadesmar python3 - < dump_window_shadesmar.py > window.json`
   (edit the session-id LIKE pattern inside). Read-only against state.db.
2. `extract_dryrun.py window.json [model]` — runs on xr7620; sends the
   window through the gateway with the draft extraction prompt (temp 0)
   and prints tier-classified facts. Needs `GYRUS_KEY` env
   (from /data/docker/gyrus/.env).

## Dry-run #1 results (2026-08-11, NQISRC Directors Panel window, 22 msgs)

| | vllm/qwen-35b (thinking off) | kaiju/nemotron:70b |
|---|---|---|
| Facts extracted | 4 | 6 |
| Precision | 100% (nothing false/noise) | 100% |
| Conference domain facts | **0 — skipped them all** | 4 (panel roster + 3 strategic insights) |
| Contact emails | 2 | 0 |
| Tone preference | yes | yes |
| Outlook EOD-summary format preference | **missed** | **missed** |
| JSON discipline | clean | needed fence-tolerant parsing |

## Dry-run #2 (2026-08-11, same window): does scale fix the miss?

Ken's question: does extraction need 120B-class or greater? Tested 120B and
253B on the v0 prompt, and re-ran the 70B on a v0.1 prompt whose only change
is a recurrence-aware rule ("a format request referencing a prior instance
is a preference — extract it").

| | qwen-35B v0 | nemotron:70B v0 | nemotron-120B v0 | **nemotron:70B v0.1** |
|---|---|---|---|---|
| Facts | 4 | 6 | 4 | **7** |
| Domain facts (panel/insights) | 0 | 4 | **0** | 4 |
| EOD format preference | miss | miss | **caught** (as procedural, full section list) | **caught** |
| Contact emails | 2 | 0 | 2 | 0 |
| Precision | 100% | 100% | 100% | 100% |

(253B untestable: NVIDIA retired the hosted function — the account's key is
fine; the endpoint is gone. Gateway fallbacks repointed to
`nemotron-3-ultra-550b` the same day.)

**Answer: no, scale is not the lever.** The 120B *lost* the domain facts the
70B caught while finding the format preference the 70B missed — scale
changed which facts got attention, not extraction quality. The v0.1 prompt
rule got the 70B to strictly the best result of any run (everything except
the two emails). At single-window scope, prompt design > model size once
past the flash tier; the residual gap (emails) is a union/second-pass
question, not a bigger-model question.

Working recommendation for M1: `kaiju/nemotron:70b` + iterated prompt as
the primary extractor; evaluate union-with-qwen-35b (cheap, catches the
entity-string tail) in the golden-set bake-off. Keep 120B as a bake-off
contender, not the default.

Findings that shape M1:
- **Model choice dominated prompt design at v0.** The judge-class model saw
  the domain knowledge; the flash model discarded it. Extraction is an
  offline pass — latency is cheap — so it gets the big model (or a union of
  two). Bake-off belongs in this harness.
- **Recurring-format preferences hide inside task requests.** "Format it
  like yesterday's Outlook summary" IS a preference once it recurs; the v0
  discernment rule ("skip formatting requests bound to this single task")
  eats it. Needs a recurrence-aware rule or a cross-session signal.
- Real windows contain duplicate sends, [CONTEXT COMPACTION] blocks, and
  ASR-sludge transcripts — the prompt's dedupe/skip rules handled these
  correctly in both runs.
- Use structured output / response_format if the gateway supports it, else
  keep the tolerant parser.

## Dry-run #3 (2026-08-11): full golden-set matrix + Lightning + serving facts

Six real windows × configs, all on the v0.1 prompt. Facts per window
(cron windows should yield ~0):

| window | nemotron:70b | nemotron-lightning | qwen-35b | nemotron-120b |
|---|---|---|---|---|
| nqisrc-panel | **8** (38s) | 1 (6s) | lane down | 0 (thinking ate budget) |
| conference-cleanup | **7** (31s) | HTTP 400 | lane down | — |
| day3-summaries | **6** (29s) | HTTP 400 | lane down | HTTP 400 |
| recent-other | **6** (28s) | 0 (5s) | lane down | truncated JSON |
| cron-monday-brief | **0** ✓ | 0 ✓ | lane down | — |
| cron-quantum-radar | 4 (noise — see below) | 0 | lane down | — |

Serving facts that decided it:
- kaiju `nemotron:70b` = llama-3.1-nemotron-70b **Q4_K_M**, model max 128k ctx,
  served at **64k** (`OLLAMA_CONTEXT_LENGTH=65536`) — no silent-truncation risk
  at our window sizes, and the box is otherwise idle.
- GB10 `vllm/nemotron-120b` is a THINKING model behind a tight serving window:
  4k gen budget → reasoning consumed it (empty/truncated JSON); 9k gen budget →
  400 (prompt+gen exceeds max seq len). Also: it is Pip's future MAIN
  interactive model (integration Phase 1) — extraction load there competes
  with Pip's own lane. GB10 has no nemotron-70b (its `llama-70b` is plain
  Llama 3.3), so a same-model quant comparison isn't available.
- Lightning (30B-A3B): fastest by far (5-6s) and passed the cron probes, but
  0-1 facts on real windows — inert, not discerning. Fine for the flash lane;
  wrong tool for a recall-critical offline pass. qwen-35b lane was down all
  afternoon (displaced from GB10 by the Lightning load — batch-claimed GPUs
  mean lanes come and go; extraction jobs need queue/retry + a fallback model).

**DECISION (pending Ken's answer key): `kaiju/nemotron:70b` + v0.1 prompt is
the extraction workhorse.** Structural findings folded into M1 requirements:
1. **Backfill must filter `sessions.source='cron'`** — the radar probe showed
   automated output extracted as "memories" (news clippings + preferences
   inferred from the cron job's own prompt, mislabeled `ken_said`).
2. **Chunking budget**: live path is per-turn (naturally small); backfill uses
   sliding windows (~12 msgs, 2-msg overlap, 24k-char cap) with store-side
   dedupe. Never feed whole sessions.
3. Provenance rule needed: scripted/system-authored text is never `ken_said`.
4. Extraction runner needs retry + model fallback (lanes are batch-claimed).

## Test phase result (2026-08-12): PASS

Answer key graded (Ken delegated the detail pass; grades + caveat live in
goldens/GRADING-SHEET.md, local-only): across the four real windows the
champion config extracted 27 facts — 26 keepers, 1 redundant, 0 fabricated.
**Keep-rate 96% vs the 80% gate; noise 0% vs the 5% ceiling.** The clean cron
probe extracted nothing (correct); the radar probe remains the standing
regression case for source filtering. All recall gaps were entity/reference-
class (contact emails, library names, speaker attributions) — the union-
second-pass case. Grading added one taxonomy requirement: a "relayed"
provenance value, because Ken transcribing a conference talk is not Ken
asserting facts (ken_said currently conflates them).

## Test phase design (the original gate)

- Golden set: ≥5 windows across session types (conference deep-dive, ops
  work, casual check-in, cron output — cron must extract ~nothing).
- Grade precision AND recall per tier against a human (Ken) answer key —
  including "should NOT extract" items. Ken review of extracted facts is
  the acceptance test; target: he'd keep ≥80% and finds <5% noise.
- Model bake-off: nemotron:70b vs qwen-35b vs union-of-both.
