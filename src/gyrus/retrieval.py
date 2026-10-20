"""Hybrid retrieval — keyword + semantic + entity graph, fused. Never one leg.

Non-negotiable #2, and greenfield by necessity: verification (2026-08-11)
showed gemma-forge's ranker is NOT hybrid — it scores lexical prefixes of
STIG rule IDs. Its docstring's anti-embedding argument is about rule-ID
strings collapsing on shared tokens and does not transfer to natural-language
memories. What DOES transfer is its shape: cheap SQL prefilter, rank in
Python, and a historical-outcome term that the dream pass later learns.

Fusion is Reciprocal Rank Fusion rather than a weighted sum of raw scores.
BM25-ish ts_rank_cd values and cosine similarities are not commensurable —
gemma-forge's own tuning pain came from a weighted sum over a base term that
was "usually 0 or >= 0.6". RRF only reads each leg's ORDER, so a leg being
absent (no embedding, no entity hit) degrades the result instead of
corrupting the arithmetic.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from . import gateway
from .config import settings

logger = logging.getLogger(__name__)

RRF_K = 60          # canonical smoothing constant; rank 1 -> 1/61, rank 10 -> 1/70
LEG_WEIGHTS = {"keyword": 1.0, "semantic": 1.0, "graph": 1.2}
# The graph leg leads on purpose: for a personal agent the entity match
# ("Kaiju", "gemma-forge", "Kelsey") is usually a stronger relevance signal
# than either lexical overlap or topical similarity (ARCHITECTURE ss.7).

_WORD = re.compile(r"[A-Za-z0-9_./:-]{2,}")


@dataclass
class Recall:
    memory_id: int
    tier: str
    fact: str
    provenance: str
    score: float
    legs: list[str]


def _or_query(query: str) -> str:
    """Turn a natural-language question into OR-semantics websearch syntax.

    `websearch_to_tsquery` ANDs its terms, so "how do I like my end of day
    summaries formatted" demanded every stem and matched nothing — measured
    2026-08-12, the keyword leg went silent on exactly the conversational
    phrasing an agent actually sends. Ranking (ts_rank_cd) sorts out which
    partial matches are good; the query's job is to find candidates.
    """
    # A leading '-' is websearch's NOT: "ls -la" became `!'la'`, which matched
    # 18,305 of 18,310 memories at rank 0 and flooded the pool (review C8).
    words = [w.lstrip("-") for w in _WORD.findall(query.lower())]
    words = [w for w in words if len(w) > 2]
    return " or ".join(dict.fromkeys(words))[:2000]


# Candidate pools are drawn PER FAMILY (review C3, 2026-10-20). With the
# knowledge tier at 78% of the store, each leg's tier-blind top-40 was 28-37
# knowledge rows, and the 0.6 knowledge weight only applies to memories that
# made a pool — a personal memory ranked 41st everywhere scored zero. Each leg
# now runs once for the personal tiers and once for knowledge; RRF ranks are
# per list, so a personal rank-1 and a knowledge rank-1 start equal and the
# tier weight then decides.
_FAMILY_SQL = {"personal": "tier <> 'knowledge'", "knowledge": "tier = 'knowledge'"}


async def _keyword(conn, query: str, limit: int, family: str = "personal") -> list[dict[str, Any]]:
    q = _or_query(query)
    if not q:
        return []
    rows = await conn.fetch(
        "SELECT id, tier, fact, provenance,"
        "       ts_rank_cd(fts, websearch_to_tsquery('english', $1)) AS s"
        " FROM memories"
        f" WHERE retired_at IS NULL AND {_FAMILY_SQL[family]}"
        "   AND fts @@ websearch_to_tsquery('english', $1)"
        " ORDER BY s DESC LIMIT $2", q, limit)
    return [dict(r) for r in rows]


async def _semantic(conn, query_vec: str | None, limit: int,
                    family: str = "personal") -> list[dict[str, Any]]:
    if query_vec is None:
        return []
    # A cosine FLOOR, not just a top-k. Nearest-neighbour always returns
    # something: with the floor off, unrelated memories at cosine ~0.3 still
    # made the top-40 and then filled recall slots the agent actually reads
    # (measured 2026-08-12 — the "filler" rows in every weak query). Vector
    # search answers "closest", never "close enough"; the threshold is what
    # turns it into a relevance test.
    rows = await conn.fetch(
        "SELECT id, tier, fact, provenance, 1 - (embedding <=> $1::vector) AS s"
        f" FROM memories WHERE retired_at IS NULL AND {_FAMILY_SQL[family]}"
        "   AND embedding IS NOT NULL"
        "   AND 1 - (embedding <=> $1::vector) >= $3"
        " ORDER BY embedding <=> $1::vector LIMIT $2",
        query_vec, limit, settings.semantic_floor)
    return [dict(r) for r in rows]


async def _graph(conn, query: str, limit: int, family: str = "personal") -> list[dict[str, Any]]:
    """Entity leg: memories tagged with an entity the query mentions.

    Matching is on the normalized entity appearing in the query text, so
    multi-word entities ("Dell Federal", "gemma-forge") work without the
    caller tokenizing them correctly.
    """
    # Pad both sides so matching is on WORD boundaries. Bare substring
    # matching had the entity "chat" firing on the query "SalesChat weekly
    # questions" (measured 2026-08-12) — every such false hit spends one of
    # the five recall slots the agent actually sees.
    q = " " + " ".join(re.sub(r"[^a-z0-9_./:-]+", " ", query.lower()).split()) + " "
    if len(q) < 4:
        return []
    # Inverse document frequency: "ken" and "hermes" tag ~every memory in a
    # personal agent's store, so their match says nothing. A rare entity
    # ("NQISRC", "SalesChat") is the strongest relevance signal we have.
    # ADR-0013: one-hop entity expansion from the nightly graph projection.
    # entity_relations is a small Postgres table (migration 0008) written
    # back by graph.enrich() — the hot path reads a co-occurrence result,
    # never the graph itself. Expanded matches carry HALF weight: a related
    # entity is a lead, not a mention. Empty table = no expansion, cleanly.
    rows = await conn.fetch(
        "WITH df AS (SELECT normalized, count(DISTINCT memory_id) AS n"
        "            FROM memory_entities GROUP BY 1),"
        "     total AS (SELECT GREATEST(count(*), 1)::float AS n FROM memories"
        "               WHERE retired_at IS NULL),"
        # Review D3 (2026-10-20): IDF alone was not enough — "ken" tags 9% of
        # the store and still carried ln(1/0.09) = 2.4, enough to pull 40
        # arbitrary Ken-facts into the pool and win the agreement bonus. An
        # entity on more than graph_entity_df_cap of live memories is ignored.
        "     hits AS (SELECT normalized, 1.0 AS wt FROM df"
        "              WHERE length(normalized) >= 3"
        "                AND df.n < (SELECT n FROM total) * $3"
        "                AND position(' ' || normalized || ' ' in $1) > 0),"
        "     expanded AS ("
        "       SELECT er.related AS normalized, 0.5 AS wt"
        "       FROM hits JOIN entity_relations er ON er.entity = hits.normalized"
        "       WHERE er.related NOT IN (SELECT normalized FROM hits)),"
        "     matched AS (SELECT * FROM hits UNION ALL SELECT * FROM expanded)"
        " SELECT m.id, m.tier, m.fact, m.provenance,"
        "        sum(mt.wt * ln((SELECT n FROM total) / df.n))::float AS s"
        " FROM matched mt"
        " JOIN memory_entities e ON e.normalized = mt.normalized"
        " JOIN memories m ON m.id = e.memory_id"
        " JOIN df ON df.normalized = e.normalized"
        f" WHERE m.retired_at IS NULL AND m.{_FAMILY_SQL[family]}"
        " GROUP BY m.id, m.tier, m.fact, m.provenance"
        " HAVING sum(mt.wt * ln((SELECT n FROM total) / df.n)) > 0"
        " ORDER BY s DESC, m.id DESC LIMIT $2", q, limit,
        float(settings.graph_entity_df_cap))
    return [dict(r) for r in rows]


_VEC_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()
_VEC_CACHE_MAX = 512


async def _query_vector(query: str) -> list[float] | None:
    """Embed a query, cached, under a deadline the recall path can afford."""
    key = " ".join(query.lower().split())[:500]
    if key in _VEC_CACHE:
        _VEC_CACHE.move_to_end(key)
        return _VEC_CACHE[key]
    vec = (await gateway.embed([query], timeout=settings.recall_embed_timeout,
                               attempts=1))[0]
    if vec is None:
        logger.info("semantic leg skipped (embedder over deadline); serving keyword+graph")
        return None
    _VEC_CACHE[key] = vec
    _VEC_CACHE.move_to_end(key)
    while len(_VEC_CACHE) > _VEC_CACHE_MAX:
        _VEC_CACHE.popitem(last=False)
    return vec


async def search(conn, query: str, *, k: int | None = None,
                 pool: int | None = None) -> list[Recall]:
    """Rank memories for a query. Empty query or empty store -> []."""
    k = k or settings.recall_k
    pool = pool or settings.recall_pool
    if not query or not query.strip():
        return []

    # The semantic leg gets a SHORT deadline of its own. Keyword and graph are
    # pure Postgres (~80 ms); the query embedding rides a lane that other work
    # can saturate — measured 2026-08-12, a backfill on the same box pushed it
    # past 40 s and recall returned nothing at all. "Never vector-only" has to
    # mean "never vector-DEPENDENT" too, or the leg meant to add relevance
    # becomes the leg that can veto it.
    vec = gateway.to_pgvector(await _query_vector(query))
    # Knowledge gets a smaller pool: it is reference the agent can reach for,
    # not what should fill the candidate list (ADR-0006).
    kpool = max(5, pool // 2)
    legs = {
        ("keyword", "personal"): await _keyword(conn, query, pool, "personal"),
        ("keyword", "knowledge"): await _keyword(conn, query, kpool, "knowledge"),
        ("semantic", "personal"): await _semantic(conn, vec, pool, "personal"),
        ("semantic", "knowledge"): await _semantic(conn, vec, kpool, "knowledge"),
        ("graph", "personal"): await _graph(conn, query, pool, "personal"),
        ("graph", "knowledge"): await _graph(conn, query, kpool, "knowledge"),
    }

    fused: dict[int, dict[str, Any]] = {}
    for (leg, _family), rows in legs.items():
        w = LEG_WEIGHTS[leg]
        for rank, row in enumerate(rows, start=1):
            entry = fused.setdefault(row["id"], {"row": row, "score": 0.0, "legs": []})
            entry["score"] += w / (RRF_K + rank)
            entry["legs"].append(leg)

    if not fused:
        return []

    # Learned-quality prior. Neutral at the 0.5 default, so the ranker is
    # wired for the dream pass's signal before that signal exists (M2/M3).
    ids = list(fused)
    priors = {r["id"]: (r["confidence"], r["weight"])
              for r in await conn.fetch(
                  "SELECT id, confidence, weight FROM memories WHERE id = ANY($1::bigint[])", ids)}
    # Knowledge is down-weighted vs the personal tiers (ADR-0006): a fact about
    # Ken outranks a fact about the world when both match a query. Personal
    # memory is what makes the agent feel like it knows YOU; knowledge is
    # reference the agent can reach for, not the first thing it should surface.
    tier_weight = {"procedural": 1.0, "factual": 1.0, "preference": 1.0,
                   "open_loop": 1.0, "knowledge": 0.6}
    for mid, entry in fused.items():
        conf, weight = priors.get(mid, (0.5, 1.0))
        entry["score"] *= tier_weight.get(entry["row"]["tier"], 1.0)
        # Agreement bonus: independent legs converging on the same memory is
        # the strongest relevance evidence in the system — the top hit for
        # every good query in testing was a 2- or 3-leg agreement, and the
        # noise was always a lone leg. This is also exactly why the hybrid is
        # non-negotiable: one leg can be confidently wrong, three rarely are.
        agreement = 1.0 + 0.5 * (len(set(entry["legs"])) - 1)
        entry["score"] *= (0.5 + conf) * weight * agreement

    ordered = sorted(fused.items(), key=lambda kv: (-kv[1]["score"], kv[0]))[:k]
    return [Recall(memory_id=mid, tier=e["row"]["tier"], fact=e["row"]["fact"],
                   provenance=e["row"]["provenance"], score=round(e["score"], 6),
                   legs=sorted(set(e["legs"])))
            for mid, e in ordered]


def is_control(session_id: str, query: str) -> bool:
    """ADR-0014 control arm: deterministic 1-in-N on (session, query). The
    same question in the same session lands in the same arm, so a retried
    prefetch cannot flip it, and the split is reproducible from the logged
    rows alone. 0 disables."""
    n = settings.recall_control_every
    if n <= 0:
        return False
    import zlib
    return zlib.crc32(f"{session_id}\x00{query.strip()[:500]}".encode()) % n == 0


async def log_retrievals(conn, recalls: list[Recall], *, query: str,
                         session_id: str | None, withheld: bool = False) -> None:
    """Record what was recalled. M3's credit assignment reads these rows.

    Also bumps recall bookkeeping on the memory itself — cheap here, and it
    means the dream pass can see "retrieved but never useful" without a join.

    `withheld` (ADR-0014): the control arm. The rows are logged so the
    comparison knows what WOULD have been shown, but the memory was not
    shown, so it earns no demand and is never scored as followed.
    """
    if not recalls:
        return
    await conn.executemany(
        "INSERT INTO memory_retrievals (memory_id, session_id, rank, score, query, withheld)"
        " VALUES ($1, $2, $3, $4, $5, $6)",
        [(r.memory_id, session_id, i, r.score, query[:2000], withheld)
         for i, r in enumerate(recalls, start=1)])
    if withheld:
        return
    await conn.execute(
        "UPDATE memories SET recall_count = recall_count + 1, last_recalled_at = now()"
        " WHERE id = ANY($1::bigint[])", [r.memory_id for r in recalls])


def render(recalls: list[Recall]) -> str:
    """Format recalls for injection into the agent's context.

    Provenance is rendered, not hidden: a claim Ken relayed from a conference
    speaker must not read like something Ken asserted (ADR-0002's honesty
    guardrail, applied at the point of use).
    """
    if not recalls:
        return ""
    label = {"ken_said": "Ken", "relayed": "relayed", "observed": "observed",
             "assistant_suggested": "unconfirmed"}
    lines = ["[gyrus] relevant memory:"]
    for r in recalls:
        lines.append(f"- ({r.tier}/{label.get(r.provenance, r.provenance)}) {r.fact}")
    return "\n".join(lines)
