# Audit brief — 2026-08-15

**For the session that does the re-assessment.** Written at the end of a long
build session, by the agent that found most of these defects and *caused* two
of them. Treat every number here as a lead to re-verify, not as a result to
inherit — that is the whole point of what follows.

Repo state at writing: `main` @ `4644248`, working tree clean, 13 commits
unpushed. Service healthy at `10.0.13.11:8000`:
`{"turns":1841,"pending":0,"memories":12886,"unembedded":0}`.

---

## 1. Read this section first: the pattern

gyrus does not have a scattering of unrelated bugs. Every defect found today is
the same defect in different clothing:

> **A failure produces an empty or zero result, and that zero is then recorded
> as a legitimate answer.**

Eight instances, all confirmed:

| # | Where | The failure | What it looked like |
|---|---|---|---|
| 1 | `gateway.chat_json` | gateway unreachable | `[]` → `/v1/extract-window` stamped turns extracted. **The backlog erases itself.** |
| 2 | `gateway.chat_json` | thinking model returns empty | read as "nothing worth keeping" |
| 3 | `extract_dryrun.py` | `\[.*\]` regex can't parse fenced/near-JSON | real model output scored as **0 facts**, for *both* models |
| 4 | eval matrix | model id `vllm/nemotron-lightning` → **403** | written down as "the flash tier extracted almost nothing", load-bearing for four months |
| 5 | `backfill_state_db.py` | resumed run collects no ids | `mark-extracted` over `[]` marks nothing, returns success |
| 6 | `worker._sweeper` | `meta->>'backfill' <> 'true'` exclusion | 465 turns invisible for 3 days, no error, `extract_error` NULL |
| 7 | `backfill_state_db.py` | `except: pass` around the marking call | failure swallowed entirely |
| 8 | `consolidate()` | report dir not mounted | `mkdir` succeeds, reports evaporate on rebuild |

And a ninth, found last and probably the most consequential for the store:

| 9 | `extraction.persist` | embedder unavailable | dedupe is guarded by `if pgvec is not None`, so the near-duplicate check is **skipped entirely** and the fact inserts unconditionally. `_embed_sweeper` supplies the vector afterwards, so the memory looks deduped forever after. |

**What to do with this.** When auditing, do not ask "does this code work?" Ask
**"what does this code do when its dependency is unavailable, and is that
outcome distinguishable from success?"** Every one of the nine above passes the
first question and fails the second. Good places to point that question:
`retrieval.py` (does a failed embed silently degrade recall to keyword-only and
report success?), `outcomes.py`, `consolidate.py`, and the thalamus pull.

---

## 2. Claims ledger

### Verified today (trust, but the method is in the commits — check it)

| Claim | Evidence |
|---|---|
| Extraction should stay on `kaiju/nemotron:70b` | ADR-0010; 6 golden windows, production path |
| `lab/flash` ≡ `vllm/nemotron-lightning-l4` — one backend, two names | byte-identical facts, latencies matching to 0.1s |
| Fast lane is **1.9x**, not the 9x its tok/s implies | these windows are prefill-bound (12–24k chars in, short out) |
| Fast lane drops the JSON contract on 2/6 windows and files world knowledge as `procedural` | ADR-0010 |
| `kaiju/gpt-oss:120b` (union) earns its place | 6 windows; returns the reference layer (rosters, a DOI, contact addresses) the 70B walks past — and is *faster* than the 70B |
| `vllm/nemotron-120b` (fallback) **times out** on 4/6 windows at the 300s ceiling | ADR-0010 addendum |
| 465 stranded turns drained; `pending` 0 and holding through a ~1,900-memory email ingest | `/health` |

### Discredited today (do not cite these)

| Claim | Why it fell |
|---|---|
| "the flash tier extracted almost nothing" | a 403 model id recorded as a quality verdict |
| "the 120B lost the domain facts the 70B caught" | **one** window, on the **v0** prompt; the matrix run scored that lane `thinking ate budget` / `HTTP 400` / `truncated JSON` / never-run |
| the 70B correctly suppresses cron windows (0 facts) | a parse artifact; it extracted facts the harness scored as zero. **Cron suppression has never worked.** |
| prompt-lineage figures — "96% keep-rate, 0% noise", "7–8 facts" | same broken instrument; **unverified, not disproven** |

### Never tested, and load-bearing

- Whether the extraction prompt is actually *good*. All evidence for it came
  through the broken harness.
- Whether the **store** is good. Nobody has graded the memories themselves.
  This is the gap that matters most.
- The firehose relevance floor (`0.55`) — never validated.
- The dedupe threshold (`0.93`) — now known to be leaving duplicates through.

### Does **not** depend on the broken instrument (architecture stands)

ADR-0002 tier-by-signal-source · ADR-0001 port-don't-rebuild · hybrid retrieval
· offline consolidation · the schema · the provider/MCP shape · ADR-0005
embeddings (that came from source verification, not a bake-off) · the
`source_key` independence work (ADR-0006/migration 0006 — driven by an observed
29× templated-footer defect, a real signal, not a bench).

**The architecture is in better shape than the evidence base.** This is not a
broken project; it is a project whose verification layer was never itself
verified.

---

## 3. The store, as it actually is

```
total (retired_at IS NULL)      12,886
  knowledge tier                 9,309   72.2%
  from thalamus (source_ref)     8,427   65.4%
  personal tiers                 3,577   27.8%
    factual                      1,833
    procedural                     644    <- the only falsifiable tier
    preference                     595
    open_loop                      505
```

By source, with first/last seen:

| source | n | ingested |
|---|---|---|
| github | **6,344** | 2026-08-14 — **one day** |
| email | 1,903 | 2026-08-15 — today |
| industry | 536 | 08-12 → 08-13 |
| arxiv | 267 | 08-12 → 08-14 |
| conversation | 173 | today |
| podcast | 47 | 08-12 → 08-13 |
| conference | 39 | 08-12 → 08-13 |

**Three facts a re-assessment should sit with:**

1. **gyrus is currently 72% a knowledge base and 28% a personal memory.** The
   thesis (ADR-0002, the falsifiable claim in BRIEF.md) is about the 28%. No
   document states this.
2. **64% of the store arrived in the last 48 hours**, through the *trusted*
   path, which by design bypasses the relevance gate entirely (ADR-0008), using
   a prompt whose quality numbers are unverified. github alone is 49% of
   everything gyrus believes, from a single day's ingest.
3. **`outcome_scored` is 0.** The procedural tier has no ground-truth signal
   and cannot get any from backfill — the source capture stored only
   `role`/`content`, so there are no tool-call records to score. The curve in
   BRIEF.md needs *live* usage; M4/M5 are its prerequisite, not a detour.

### The duplicate finding

A 400-memory sample, nearest same-tier neighbour by cosine:

| | count | share |
|---|---|---|
| ≥ 0.93 (production's own dedupe threshold) | 61 | **15%** |
| ≥ 0.90 | 143 | 36% |
| mean nearest-neighbour similarity | 0.849 | |

15% of the store is duplicates the system's own rule says should not exist.
Suspected mechanism is #9 in the pattern table. **Consequence for the audit:
memory count measures nothing.** Any "gyrus knows N things" figure is soft
until this is characterised.

Corroborating signal from the union delta (`tools/extraction-eval/union_delta.py`):
of gpt-oss's 65 facts across the golden windows, **64 survive dedupe** against
the 70B's 35 — 2% absorption. Two competent models on identical input sharing
2% of their output, with some survivors being the same claim reworded and both
stored.

---

## 4. Open defects — recorded, deliberately unfixed

Ranked by (impact on the store) × (cheapness to fix). All are in TASKS.md.

1. **Fallback lane times out** — `vllm/nemotron-120b` exceeds the 300s
   `chat_json` ceiling on 4/6 windows. The lane covering a kaiju outage would
   itself fail. Raise its timeout or repoint `extract_fallback_model`.
   *Contained; ~20 minutes. Take this one anytime.*
2. **Dedupe hole (#9)** — confirm the mechanism before fixing. Two questions
   entangled: should `persist` refuse to insert when it cannot embed (backpressure)
   rather than inserting undeduped, and is 0.93 the right threshold at all?
3. **Cron suppression** — the prompt says automated output yields nothing; the
   70B returns 6 facts on `cron-monday-brief` and the fast lane 13, the latter
   attributing a scheduled job's own brief to `ken_said`. `worker._extract_turn`'s
   `platform='cron'` filter protects the live path, so this is defense-in-depth
   today, **not an active leak** — but `/v1/extract-window` has no such guard.
   Prompt change ⇒ needs its own golden-set pass.
4. **Prompt-lineage numbers unverified** — re-run the golden set under
   `bench_lanes.py` and correct or confirm.

---

## 5. Fixed today — do not re-litigate

| Commit | What |
|---|---|
| `4d3bdbb` | 7 review findings: `windows()` KeyError (broke the import tool on *every* invocation), double-claimed turns, sweeper/repair-tool race (lease), missing cron filter, unordered exact-hash locks, window self-corroboration, ingest 500-on-GatewayError |
| `ab691a1` | dream reports persisted (volume bind); **empty model content is now a failure, not zero facts** |
| `129a504`, `4644248` | ADR-0010 + addendum; `bench_lanes.py`, `union_delta.py` |
| `02a15fd` | M1.5 backfill gap closed (465 → 0) |

Also fixed earlier in the session and swept into other sessions' commits
(`38718e5`, `b401daa`): `GatewayError` on no-lane-answered, `/v1/extract-window`
503 instead of stamping, sweeper grace period, deadlock ordering + retry.

Two of the seven in `4d3bdbb` were **introduced by me** earlier the same
session and caught only by review — I verified the tool I was *using*, not the
tool I *changed*. Assume the same failure mode is possible in anything here.

---

## 6. Recommended scope, in order

**Start read-only. Start from the artifact, not from the models.**

1. **Grade the store.** Stratified sample (~100–150) across tier × source.
   Every model decision was a proxy for "does this produce good memories", and
   there are now 12,886 real memories — a far better test set than 6 golden
   windows. Output: keep/drop/wrong-tier rates *per source*. This single pass
   tells you whether anything else on this list matters.
2. **Thalamus.** 65% of the store, never reviewed, largely ungated by design.
   Read ADR-0007/0008 against what the github and email lanes actually produced.
3. **Characterise the duplicates** (#9) and decide the threshold question.
4. **Only then, models** — and only if (1) says extraction quality is the
   problem. `bench_lanes.py` makes that ~5 minutes of GPU time.

**Do not:**
- start by re-running lane bake-offs — that question is largely settled, and in
  favour of the status quo
- rewrite the eval harness before deciding what needs measuring
- trust `run_matrix.py` / `extract_dryrun.py` for anything (frozen v0 prompt,
  weak parser) — `bench_lanes.py` replaced them for lane work
- treat memory counts as progress

---

## 7. Reproducing the evidence

```bash
# store composition / duplicate sample — run inside the container
docker exec -i gyrus python /tmp/q.py   # see scratchpad q.py, or use asyncpg directly

# lane bench (production prompt + salvage parser, fallback disabled, warmed)
docker exec gyrus mkdir -p /tmp/eval
docker cp tools/extraction-eval/bench_lanes.py gyrus:/tmp/eval/bench_lanes.py
docker cp tools/extraction-eval/goldens gyrus:/tmp/eval/goldens
docker exec gyrus python /tmp/eval/bench_lanes.py --max-tokens 8000 \
  --models kaiju/nemotron:70b vllm/nemotron-120b kaiju/gpt-oss:120b

# does the union second pass earn its cost?
docker exec gyrus python /tmp/union_delta.py
```

`goldens/` is **gitignored** (extracted facts carry personal content) — the
windows exist on disk at `tools/extraction-eval/goldens/`, results alongside.

Gotchas that cost time today: `docker cp src dest/` nests when `dest` exists;
the container runs the **installed** package, so source edits need
`docker compose up -d --build`; `docker exec` output does not appear in
`docker logs`; kaiju is on-demand (~50s cold), so warm before timing anything.

---

## 8. Questions for Ken

1. **Is 72%-knowledge / 28%-personal the intended shape?** If yes, BRIEF.md and
   ADR-0002 should say so, and retrieval should be evaluated against it. If no,
   the trusted-path volume needs a gate.
2. **Tier indirection** — the lab contract says request a *tier*, never a model
   name; gyrus hardcodes four model names. The key currently grants `lab/flash`
   but **not** `lab/embed` or `lab/reason`, so a full move needs scope.
3. **Should `persist` apply backpressure when it cannot embed** — refuse the
   write rather than insert undeduped? That is a durability-vs-correctness call.
4. **Push?** 13 commits are unpushed on `main`.
