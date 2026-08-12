# 01-code-findings

_(empty — Fable writes here; flush after every finding)_

## F1 — Backfill memories have no turn-level provenance [CONFIRMED, medium]
`tools/backfill_state_db.py:146` passes `turn_ids: []` to `/v1/extract-window`,
so `extraction.persist()` writes `source_turn_id = NULL`. Measured: 2,262 of
2,568 live memories (88%) have `source_turn_id IS NULL`; 0 lack a session link.
Impact: M4 contradiction/corroboration and any audit trail lose turn-level
resolution for the entire historical corpus; only live-path memories trace to a
turn. Fix path: backfill knows the window's turn ids (it posts the turns first)
— thread them through; for the existing corpus, a repair join via
(session_id, text overlap) is possible but lossy. Severity medium: the data is
degraded, not wrong.

## F2 — Memory store is readable by anyone on the network, no auth [CONFIRMED, high-context]
`curl http://10.0.13.11:8000/v1/memories?q=email` from any LAN/DMZ host returns
Ken's memories — including contact addresses and preferences — with no
credential. The API also accepts unauthenticated WRITES (`POST /v1/turns`), so
any tenant could poison Pip's memory. Within a single-operator lab this is
survivable; it becomes untenable the moment M5's MCP face or any second tenant
arrives, and memory POISONING is an integrity issue today: a planted "fact"
would be injected into Pip's context with (provenance) authority. Cheap
mitigation now: bearer token in /data/docker/gyrus/.env, checked by middleware;
provider sends it. Queued as H1 in the handoff.

## F3 — Semantic leg silently returns ~29% of its true candidates [CONFIRMED, high]
`migrations/0002_semantic.sql:56` creates `ivfflat (lists=64)`; nothing ever
sets `ivfflat.probes`, so every query runs at the default probes=1. Paired
measurement (same 8 query vectors, top-10 at probes=1 vs probes=64):
**28.8% overlap**. The semantic leg has been missing ~70% of its best matches
on every recall since the index went in — undetectable from outside because
RRF fusion just quietly reweights toward the other legs. This also degrades
write-time near-dup detection (`extraction.persist` uses the same index), which
partially explains the observed duplicate NQISRC memories beyond the embedder-
stall explanation the author logged. Fix: SET LOCAL probes (or switch to HNSW)
— see F3-fix commit.

## Verified-OK — lowercase 'or'

## F2 — ivfflat index silently drops ~72% of true nearest neighbors [CONFIRMED, HIGH]
`src/gyrus/migrations/0002_semantic.sql:47` builds
`ivfflat (embedding vector_cosine_ops) WITH (lists = 64)`. At 2,568 vectors that
is ~40 vectors/list, and pgvector defaults to `probes = 1` — the query scans ONE
list. Paired test, exhaustive seq-scan as ground truth vs the app's index path:
**recall@10 = 28.0%** (measured this session; EXPLAIN confirms the planner uses
`idx_memories_embedding`, not a seq scan). The semantic leg is therefore
returning mostly WRONG neighbors — a silent-loss failure exactly of the class the
mission says to weight highest. It was invisible because the hybrid's other two
legs carry the good queries and the author tuned on queries where they did.
Fixes, cheapest first: (1) at this scale, drop the ANN index entirely — a flat
scan of 2.5k–50k vectors is sub-10ms and gives 100% recall; (2) or raise
`ivfflat.probes` per-session (set in `_semantic`'s connection) to ~sqrt(lists);
(3) or switch to HNSW. Recommend (1) until the store is >100k rows; the author's
own latency budget (80ms for the Postgres legs) has ample room. This also means
every semantic-leg measurement in the build's eval is suspect and must be re-run
after the fix.

## F3 — Full memory store is readable unauthenticated on the DMZ [CONFIRMED, medium]
`GET /v1/memories?q=email` returned Ken's preferences incl. email addresses with
no credential (measured this session from off-host). The API has no auth at all
(`src/gyrus/api.py` — no dependency, no key check). ADR-0004 accepts LAN/DMZ
reachability, and LAN→DMZ is the trust model, but the store now holds ~2,500
extracted personal facts — a higher-value target than the M0 episodic scratch
that reachability decision was made against. Not a v1 blocker (no DMZ→outside
path), but the MCP face (M5) "leaves the LAN" and MUST NOT inherit this posture.
Flag for M5 threat model; consider a scoped token even LAN-side now.

## F4 — ~27% of the store is domain knowledge, not memory about Ken [CONFIRMED, HIGH — thesis-level]
`assistant_suggested` is 1,097 of 2,654 live memories (41%). Of those, only 389
(35%) contain ANY personal anchor (Ken/Dell/Obsidian/Pip/Hermes/etc.); the other
~710 are generic domain facts ("Qblox has public collaborations with HPE, NVIDIA,
AMD, IQM"; "ROQUO connects to Quantinuum's Reimei… links to Fugaku") or the
assistant's own engineering notes ("In score_candidate(), required_terms are
built from list(query_terms)[:6]…"). Net: **~27% of the whole store is a quantum
knowledge base, not memory about the user.**

Two-sided reading:
  - HONEST: the provenance label is correct — these are genuinely not `ken_said`,
    and `retrieval.render()` marks them "unconfirmed" at injection. ADR-0002's
    honesty guardrail HOLDS. This is not the "confidently-wrong preference"
    failure mode the author feared — it's a different one.
  - BUT: this is the RAGFlow/deep-corpus tier — which `PLAN.md` explicitly scopes
    OUT of this project — bleeding into the memory tier. It entered through the
    conference-note sessions, which are Ken transcribing external talks; the
    extractor has no notion of "this whole session is relayed knowledge, not a
    signal about the user." It is the same category the team just REJECTED in
    `docs/references/OPENBRAIN-AUDIT.md` (news-clipping bloat), re-created by a
    different path.

Why it matters for M2/M3, not just tidiness: ADR-0002 tiers by SIGNAL SOURCE,
and `assistant_suggested` domain facts have NO signal source — no ground truth,
no corroboration loop, no reason to ever be recalled-and-followed. They will sit
at confidence 0.5 forever. The dream pass therefore needs an explicit rule
("never corroborated + never recalled + no personal anchor → evict or demote to
a separate reference store"), or the procedural-tier success curve (the
falsifiable claim) gets measured against a store that is 27% inert ballast.
Recommend: either (a) a session-level "is this the user teaching me, or me
recording the world?" gate in extraction, or (b) an explicit reference tier that
retrieval can weight down. This is the single most important pre-M2 decision.

## F5 — Near-duplicates are widespread (~23%), and F2 is the root cause [CONFIRMED, HIGH]
Census on a 1/3 sample (898 memories, probes=64 exhaustive): 206 have a nearest
neighbor at cosine ≥0.93, 54 at ≥0.97. Extrapolated: ~600 near-dups at the 0.93
line store-wide — NOT the "4 known NQISRC" the build logged. Root cause is F2:
`extraction.persist()` (`src/gyrus/extraction.py:~186`) finds the merge target
with `ORDER BY embedding <=> $1::vector LIMIT 1` — the SAME ivfflat/probes=1 path
that has 28% recall. So write-time dedupe MISSES ~72% of the duplicates it is
meant to merge, whether or not the embedder stalled. The stall-skip (already
known) is a second, smaller leak. Fixing F2 (drop the index at this scale) fixes
dedupe and the semantic leg in one change. Until then the corroboration-count
signal (the factual tier's reward, ADR-0002) is undercounted: true corroborations
are landing as separate rows instead of incrementing a counter.
