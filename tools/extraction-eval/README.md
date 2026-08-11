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

## Test phase (gate for M1 "done")

- Golden set: ≥5 windows across session types (conference deep-dive, ops
  work, casual check-in, cron output — cron must extract ~nothing).
- Grade precision AND recall per tier against a human (Ken) answer key —
  including "should NOT extract" items. Ken review of extracted facts is
  the acceptance test; target: he'd keep ≥80% and finds <5% noise.
- Model bake-off: nemotron:70b vs qwen-35b vs union-of-both.
