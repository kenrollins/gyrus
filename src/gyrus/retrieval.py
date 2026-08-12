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
    words = [w for w in _WORD.findall(query.lower()) if len(w) > 2]
    return " or ".join(dict.fromkeys(words))[:2000]


async def _keyword(conn, query: str, limit: int) -> list[dict[str, Any]]:
    q = _or_query(query)
    if not q:
        return []
    rows = await conn.fetch(
        "SELECT id, tier, fact, provenance,"
        "       ts_rank_cd(fts, websearch_to_tsquery('english', $1)) AS s"
        " FROM memories"
        " WHERE retired_at IS NULL AND fts @@ websearch_to_tsquery('english', $1)"
        " ORDER BY s DESC LIMIT $2", q, limit)
    return [dict(r) for r in rows]


async def _semantic(conn, query_vec: str | None, limit: int) -> list[dict[str, Any]]:
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
        " FROM memories WHERE retired_at IS NULL AND embedding IS NOT NULL"
        "   AND 1 - (embedding <=> $1::vector) >= $3"
        " ORDER BY embedding <=> $1::vector LIMIT $2",
        query_vec, limit, settings.semantic_floor)
    return [dict(r) for r in rows]


async def _graph(conn, query: str, limit: int) -> list[dict[str, Any]]:
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
    rows = await conn.fetch(
        "WITH df AS (SELECT normalized, count(DISTINCT memory_id) AS n"
        "            FROM memory_entities GROUP BY 1),"
        "     total AS (SELECT GREATEST(count(*), 1)::float AS n FROM memories"
        "               WHERE retired_at IS NULL)"
        " SELECT m.id, m.tier, m.fact, m.provenance,"
        "        sum(ln((SELECT n FROM total) / df.n))::float AS s"
        " FROM memory_entities e"
        " JOIN memories m ON m.id = e.memory_id"
        " JOIN df ON df.normalized = e.normalized"
        " WHERE m.retired_at IS NULL AND length(e.normalized) >= 3"
        "   AND position(' ' || e.normalized || ' ' in $1) > 0"
        " GROUP BY m.id, m.tier, m.fact, m.provenance"
        " HAVING sum(ln((SELECT n FROM total) / df.n)) > 0"
        " ORDER BY s DESC, m.id DESC LIMIT $2", q, limit)
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
    legs = {
        "keyword": await _keyword(conn, query, pool),
        "semantic": await _semantic(conn, vec, pool),
        "graph": await _graph(conn, query, pool),
    }

    fused: dict[int, dict[str, Any]] = {}
    for leg, rows in legs.items():
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
    for mid, entry in fused.items():
        conf, weight = priors.get(mid, (0.5, 1.0))
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


async def log_retrievals(conn, recalls: list[Recall], *, query: str,
                         session_id: str | None) -> None:
    """Record what was recalled. M3's credit assignment reads these rows.

    Also bumps recall bookkeeping on the memory itself — cheap here, and it
    means the dream pass can see "retrieved but never useful" without a join.
    """
    if not recalls:
        return
    await conn.executemany(
        "INSERT INTO memory_retrievals (memory_id, session_id, rank, score, query)"
        " VALUES ($1, $2, $3, $4, $5)",
        [(r.memory_id, session_id, i, r.score, query[:2000])
         for i, r in enumerate(recalls, start=1)])
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
