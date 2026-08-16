"""The dream pass — offline consolidation. gyrus's distinctive contribution.

Ports the SHAPE of gemma-forge's `dream/pass_.py` + `memory/eviction.py`
(graded salience, threshold-retirement, idempotent stamp, markdown report) and
the signal-forge `consolidate.py` pattern (dry-run by default, `--commit` to
write), adapted to gyrus's schema and to **per-tier evaluators** (ADR-0002/0006):

  procedural  — outcome-driven credit (needs M3's outcome_value; NO-OP until then)
  factual     — corroboration frequency
  preference  — proxy: reuse (recall) + uncontradicted
  knowledge   — recency x retrieval-demand (needs M4 tier; NO-OP until then)

Consolidation UPDATES each memory's `confidence` (the learned prior the ranker
already reads), and SEPARATELY flags eviction candidates — soft-retire only,
and only for memories that have had a fair chance to prove value and didn't.

Non-negotiables honored: offline only (never on the turn path), idempotent via
`consolidated_at`, writes a markdown report. First contact is a DRY RUN.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import db

logger = logging.getLogger(__name__)

# --- scoring knobs (first-pass, deliberately legible — tune against the report) ---
BASE = 0.5
CORROB_STEP, CORROB_CAP = 0.06, 5      # repeated independent extraction = signal
DEMAND_STEP, DEMAND_CAP = 0.08, 5      # recalled in real use = the strongest proxy we have pre-M3
PROVENANCE = {"ken_said": 0.15, "observed": 0.05, "relayed": 0.0, "assistant_suggested": -0.10}
PERSONAL_ANCHOR_BONUS = 0.05           # a memory that actually mentions Ken's world
RECENCY_PENALTY_PER_YEAR = 0.20        # untouched memories fade; demand/corroboration offset it
EVICT_THRESHOLD = 0.33                 # below this, after a fair chance, it's a candidate
EVICT_MIN_AGE_DAYS = 21                # "fair chance" — don't retire the freshly-written
NEAR_DUP_COSINE = 0.97                 # F5: merge, don't hoard
OUTCOME_MIN_SAMPLES = 3                # gemma-forge required 5; don't let one noisy turn move confidence

_ANCHOR = ("ken", "dell", "obsidian", "pip", "hermes", "gyrus", "kaiju", "federal")
KNOWLEDGE_DEMAND_STEP = 0.07
KNOWLEDGE_RECENCY_FADE_DAYS = 180      # knowledge goes stale on a ~6-month clock


def _knowledge_utility(m: dict) -> float:
    """Knowledge tier (ADR-0006): source authority x recency x retrieval-demand.
    No outcome, no corroboration loop — demand (agent recall + human browse) is
    the only EARNED signal, and knowledge fades on a recency clock personal
    memory doesn't."""
    u = BASE
    demand = m["recall_count"] + m.get("browse_count", 0)
    u += min(demand, 6) * KNOWLEDGE_DEMAND_STEP
    # ADR-0011: recency means EVENT recency. A March story ingested in August
    # must decay as March news — created_at measures the ingest job, not the
    # news. NULL event_at (live conversation, legacy rows) keeps created_at.
    ref = m.get("event_at") or m["created_at"]
    age_days = (datetime.now(timezone.utc) - ref).days
    u -= min(age_days / KNOWLEDGE_RECENCY_FADE_DAYS, 1.0) * 0.25
    return max(0.0, min(1.0, u))


@dataclass
class Report:
    scored: int = 0
    outcome_scored: int = 0
    confidence_raised: int = 0
    confidence_lowered: int = 0
    expired: int = 0                   # ADR-0011: valid_until passed, retired
    evict_candidates: list = field(default_factory=list)
    merges: list = field(default_factory=list)
    by_tier: dict = field(default_factory=dict)
    top: list = field(default_factory=list)
    bottom: list = field(default_factory=list)


def _utility(m: dict) -> float:
    """Evidence-weighted quality in [0,1] from the signals available pre-M3."""
    u = BASE
    u += min(max(m["corroboration_count"] - 1, 0), CORROB_CAP) * CORROB_STEP
    u += min(m["recall_count"], DEMAND_CAP) * DEMAND_STEP
    u += PROVENANCE.get(m["provenance"], 0.0)
    text = (m["fact"] or "").lower()
    ents = " ".join(m["entities"] or []).lower()
    if any(a in text or a in ents for a in _ANCHOR):
        u += PERSONAL_ANCHOR_BONUS
    age_days = (datetime.now(timezone.utc) - m["created_at"]).days
    # recency penalty applies only to memories with no earned signal —
    # something recalled or corroborated has proven itself and shouldn't rot.
    if m["recall_count"] == 0 and m["corroboration_count"] <= 1:
        u -= (age_days / 365.0) * RECENCY_PENALTY_PER_YEAR
    return max(0.0, min(1.0, u))


async def consolidate(*, commit: bool = False, report_dir: str | None = None) -> Report:
    pool = await db.get_pool()
    rep = Report()
    async with pool.acquire() as conn:
        # ADR-0011: expired time-scoped facts retire BEFORE scoring — "Ken
        # wants to avoid email tonight" must not spend weeks decaying toward
        # eviction after the night has passed. Soft, like every retirement.
        if commit:
            expired = await conn.fetch(
                "UPDATE memories SET retired_at = now(),"
                " retired_reason = 'expired: valid_until ' || valid_until::date"
                " WHERE retired_at IS NULL AND valid_until < now() RETURNING id")
            rep.expired = len(expired)

        rows = await conn.fetch(
            "SELECT id, tier, fact, entities, provenance, confidence,"
            " corroboration_count, recall_count, browse_count, created_at,"
            " event_at, embedding IS NOT NULL AS has_vec"
            " FROM memories WHERE retired_at IS NULL")
        # M3 credit assignment: true ground truth for the procedural tier.
        # AVG(outcome_value * outcome_confidence) over scored retrievals per
        # memory — the gemma-forge follow-aware credit, reading exactly the
        # columns the outcome writer feeds. Where this exists it OVERRIDES the
        # proxy utility: an earned outcome beats every proxy (the whole thesis).
        # Require enough outcome samples before ground truth overrides proxy —
            # gemma-forge's follow_sample_size guard (it used 5). One failed turn
            # must not tank a memory whose execution happened to error.
        credit = {r["memory_id"]: r["c"] for r in await conn.fetch(
            "SELECT memory_id, AVG(outcome_value * outcome_confidence) AS c"
            " FROM memory_retrievals WHERE outcome_value IS NOT NULL"
            " GROUP BY memory_id HAVING count(*) >= $1", OUTCOME_MIN_SAMPLES)}
        rep.outcome_scored = len(credit)
        scored = []
        for r in rows:
            m = dict(r)
            if m["id"] in credit and credit[m["id"]] is not None:
                # map credit (~[-0.24, +0.8]) into a confidence in [0,1]
                u = max(0.0, min(1.0, 0.5 + float(credit[m["id"]])))
            elif m["tier"] == "knowledge":
                u = _knowledge_utility(m)
            else:
                u = _utility(m)
            scored.append((m, u))
            rep.scored += 1
            rep.by_tier.setdefault(m["tier"], {"n": 0, "util_sum": 0.0})
            rep.by_tier[m["tier"]]["n"] += 1
            rep.by_tier[m["tier"]]["util_sum"] += u
            if u > m["confidence"] + 0.02:
                rep.confidence_raised += 1
            elif u < m["confidence"] - 0.02:
                rep.confidence_lowered += 1
            age_days = (datetime.now(timezone.utc) - m["created_at"]).days
            if u < EVICT_THRESHOLD and age_days >= EVICT_MIN_AGE_DAYS \
                    and m["recall_count"] == 0 and m["corroboration_count"] <= 1:
                rep.evict_candidates.append((m, u))

        scored.sort(key=lambda mu: -mu[1])
        rep.top = [(m["id"], round(u, 3), m["tier"], m["fact"][:70]) for m, u in scored[:15]]
        rep.bottom = [(m["id"], round(u, 3), m["tier"], m["fact"][:70]) for m, u in scored[-15:]]

        # F5 near-duplicate merge (only meaningful with vectors)
        rep.merges = await _find_merges(conn)

        if commit:
            async with conn.transaction():
                for m, u in scored:
                    await conn.execute(
                        "UPDATE memories SET confidence=$2, consolidated_at=now(), updated_at=now()"
                        " WHERE id=$1", m["id"], u)
                for keep_id, drop_id, sim in rep.merges:
                    await conn.execute(
                        "UPDATE memories SET corroboration_count = corroboration_count +"
                        " (SELECT corroboration_count FROM memories WHERE id=$2) WHERE id=$1",
                        keep_id, drop_id)
                    await conn.execute(
                        "UPDATE memories SET retired_at=now(),"
                        " retired_reason='near-duplicate merge (F5)', superseded_by_id=$1"
                        " WHERE id=$2", keep_id, drop_id)
                for m, u in rep.evict_candidates:
                    await conn.execute(
                        "UPDATE memories SET retired_at=now(),"
                        " retired_reason=$2 WHERE id=$1", m["id"],
                        f"low utility {u:.2f} < {EVICT_THRESHOLD}, no recall/corroboration after "
                        f"{(datetime.now(timezone.utc) - m['created_at']).days}d")

    md = _render(rep, committed=commit)
    if report_dir:
        import pathlib
        p = pathlib.Path(report_dir)
        p.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (p / f"dream-{stamp}.md").write_text(md)
    logger.info("consolidation %s: scored=%d raise=%d lower=%d evict=%d merge=%d expired=%d",
                "COMMIT" if commit else "dry-run", rep.scored, rep.confidence_raised,
                rep.confidence_lowered, len(rep.evict_candidates), len(rep.merges),
                rep.expired)
    rep.markdown = md
    return rep


async def _find_merges(conn) -> list:
    """Near-duplicate pairs: keep the higher-corroboration/recall one, retire the other.

    Exact scan (no ANN — F2). Bounded: only compares within tier, only the
    nearest neighbour per memory, only pairs above NEAR_DUP_COSINE.
    """
    rows = await conn.fetch(
        "WITH nn AS ("
        "  SELECT a.id AS a_id, a.corroboration_count AS a_c, a.recall_count AS a_r,"
        "         b.id AS b_id, b.corroboration_count AS b_c, b.recall_count AS b_r,"
        "         1 - (a.embedding <=> b.embedding) AS sim,"
        "         row_number() OVER (PARTITION BY a.id ORDER BY a.embedding <=> b.embedding) AS rn"
        "  FROM memories a JOIN memories b"
        "    ON b.id <> a.id AND b.tier = a.tier AND b.retired_at IS NULL"
        "   AND b.embedding IS NOT NULL"
        "  WHERE a.retired_at IS NULL AND a.embedding IS NOT NULL"
        ") SELECT a_id, a_c, a_r, b_id, b_c, b_r, sim FROM nn"
        " WHERE rn = 1 AND sim >= $1", NEAR_DUP_COSINE)
    seen: set[int] = set()
    merges = []
    for r in rows:
        a, b = r["a_id"], r["b_id"]
        if a in seen or b in seen:
            continue
        # keep the one with more earned signal; ties → lower id (older)
        a_score = (r["a_r"], r["a_c"], -a)
        b_score = (r["b_r"], r["b_c"], -b)
        keep, drop = (a, b) if a_score >= b_score else (b, a)
        seen.add(a)
        seen.add(b)
        merges.append((keep, drop, round(r["sim"], 4)))
    return merges


def _render(rep: Report, *, committed: bool) -> str:
    lines = [
        f"# gyrus dream pass — {'COMMITTED' if committed else 'DRY RUN'}",
        f"_{datetime.now(timezone.utc).isoformat()}_", "",
        f"Scored **{rep.scored}** live memories. "
        f"confidence ↑{rep.confidence_raised} ↓{rep.confidence_lowered}. "
        f"Eviction candidates **{len(rep.evict_candidates)}**. "
        f"Near-dup merges **{len(rep.merges)}**.", "",
        "## By tier (mean utility)",
    ]
    for tier, d in sorted(rep.by_tier.items(), key=lambda kv: -kv[1]["n"]):
        lines.append(f"- **{tier}**: {d['n']} memories, mean utility "
                     f"{d['util_sum']/max(d['n'],1):.3f}")
    lines += ["", "## Top 15 by utility (should be things worth keeping)"]
    for mid, u, tier, fact in rep.top:
        lines.append(f"- `{u}` [{tier}] {fact}")
    lines += ["", "## Bottom 15 by utility (should be noise / stale)"]
    for mid, u, tier, fact in rep.bottom:
        lines.append(f"- `{u}` [{tier}] {fact}")
    lines += ["", f"## Eviction candidates ({len(rep.evict_candidates)}) — soft-retire"]
    for m, u in rep.evict_candidates[:40]:
        lines.append(f"- `{u:.2f}` [{m['tier']}|{m['provenance']}] {m['fact'][:80]}")
    if len(rep.evict_candidates) > 40:
        lines.append(f"- … and {len(rep.evict_candidates)-40} more")
    lines += ["", f"## Near-duplicate merges ({len(rep.merges)})"]
    for keep, drop, sim in rep.merges[:30]:
        lines.append(f"- keep {keep}, retire {drop} (cosine {sim})")
    return "\n".join(lines)
