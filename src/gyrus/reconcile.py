"""The reconciler — M6's evaluators + the band discriminator, one offline stage.

Three questions the dream pass could not answer until now, all forms of
"do these two memories agree?":

  1. SAME CLAIM (band 0.90–0.97): fold as corroboration — the journal-025
     discriminator, promoted from a manual tool into the nightly cycle.
  2. CONTRADICTION (factual/preference/knowledge): same subject, conflicting
     substance — "backup_keep is 3" vs "backup_keep is 5", "the watchdog is
     paused" vs "the watchdog is running". Newer event wins (ADR-0011 gives
     us honest event time); the loser is retired with superseded_by, which
     is bi-temporal "we learned better", never deletion. For the preference
     tier this IS the "corrected" proxy signal ADR-0002 asked for.
  3. RESOLUTION (open_loop): a later memory answers/completes the loop —
     the task-closure lifecycle the audit kept tripping over ("remove the
     stale entry" / "entry removed" living side by side).

Verdict discipline carried from journal-025's validation:
  - the enumeration-loss guard stays deterministic (a fold keeps ONE member;
    a one-sided identifier list cannot be folded without loss);
  - token-conflict pairs are NOT auto-distinct here — a conflicting value in
    the same sentence-shape is exactly what a contradiction looks like, so
    they go to the judge;
  - fold and supersede both require DOUBLE agreement (A/B order swap);
    disagreement means keep, always.

Procedural is excluded: that tier's truth belongs to outcome credit (M3),
and a text judge second-guessing measured pass/fail would be the
confidently-wrong failure ADR-0002 warns about.

Everything is capped per run; the nightly dream sweeper chews backlogs
incrementally rather than burning a GPU-hour in one night.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import gateway
from .config import settings

logger = logging.getLogger(__name__)

RECONCILE_TIERS = ("factual", "preference", "knowledge")
PAIR_FLOOR = 0.90          # below this, pairs are just different memories
BLIND_MERGE = 0.97         # at/above, consolidate's existing merge handles it

PAIR_SYSTEM = """You maintain a memory store. For each pair of statements about \
the same general subject, judge their relationship:

"same" — one claim, reworded or with more/less detail. Keeping only one loses \
nothing. ("Set backup_keep to 3." / "backup_keep set to 3")
"distinct" — different claims that happen to look alike: different objects, \
commands, properties, or complementary halves (a fix and its cause). Both must \
be kept. ("Use cmd+N for new file" / "Use cmd+S to save")
"contradicts" — the SAME subject and slot with INCOMPATIBLE substance: \
conflicting values, states, or a negation. They cannot both be true now. \
("backup_keep is 3" / "backup_keep is 5"; "the watchdog is paused" / "the \
watchdog is running"; "X has no partnership with Y" / "X partners with Y")
"unsure" — cannot tell from the text.

Answer ONLY a JSON array: [{"id": "<id>", "verdict": "same"|"distinct"|"contradicts"|"unsure"}]"""

RESOLVE_SYSTEM = """You judge whether an OPEN LOOP (an unresolved question, \
commitment, or follow-up captured earlier) has since been RESOLVED, using only \
the LATER memories provided as evidence. Resolved means the thing was done, \
answered, delivered, fixed, or explicitly abandoned — stated or clearly implied \
by the evidence. Related activity that does not close the loop is NOT \
resolution. When in doubt: "no" (a wrongly-closed loop is a lost reminder).
Answer ONLY a JSON array: [{"id": "<id>", "resolved": "yes"|"no", "evidence": <memory id or null>}]"""

_IDENT = re.compile(r"[a-z0-9_./\[\]-]*(?:\d|_|\.|\[|/)[a-z0-9_./\[\]:-]*", re.I)
_CAMEL = re.compile(r"[a-z]+[A-Z][A-Za-z]*")


def _critical_tokens(text: str) -> set[str]:
    toks = set()
    for w in re.findall(r"[A-Za-z0-9_./\[\]:-]+", text):
        w = w.strip(".,;:")
        if w and (any(c.isdigit() for c in w) or _IDENT.fullmatch(w) or _CAMEL.fullmatch(w)):
            toks.add(w.lower())
    return toks


def route(fact_a: str, fact_b: str) -> str:
    """'distinct' (deterministic, skip the judge) or 'judge'.

    Unlike journal-025's band tool, a conflicting-substitution pair goes TO
    the judge: same sentence-shape with a different value is either a distinct
    fact or a live contradiction, and only reading decides which.
    """
    a, b = _critical_tokens(fact_a), _critical_tokens(fact_b)
    only_a, only_b = a - b, b - a
    if (len(only_a) >= 3) != (len(only_b) >= 3):
        return "distinct"          # one-sided enumeration: folding loses the list
    return "judge"


def pick_survivor(pair_a: dict, pair_b: dict) -> tuple[dict, dict]:
    """(winner, loser) for a contradiction: newer event wins — the world
    changed and the newer memory saw it. Bi-temporal retirement makes a
    wrong call recoverable; a tie falls to the higher-signal member."""
    ta = pair_a.get("event_at") or pair_a["created_at"]
    tb = pair_b.get("event_at") or pair_b["created_at"]
    if ta == tb:
        ka = (pair_a.get("corroboration_count", 1), pair_a.get("recall_count", 0))
        kb = (pair_b.get("corroboration_count", 1), pair_b.get("recall_count", 0))
        return (pair_a, pair_b) if ka >= kb else (pair_b, pair_a)
    return (pair_a, pair_b) if ta > tb else (pair_b, pair_a)


@dataclass
class ReconcileReport:
    pairs_judged: int = 0
    folded: int = 0
    contradictions: int = 0
    loops_checked: int = 0
    loops_resolved: int = 0
    details: list = field(default_factory=list)


async def _judge_pairs(pairs: list[dict], swap: bool) -> dict[str, str]:
    out: dict[str, str] = {}
    B = 8
    for i in range(0, len(pairs), B):
        chunk = pairs[i:i + B]
        lines = []
        for p in chunk:
            fa, fb = (p["fact_b"], p["fact_a"]) if swap else (p["fact_a"], p["fact_b"])
            lines.append(f'{p["pair_id"]}:\nA: {fa}\nB: {fb}\n')
        try:
            objs = await gateway.chat_json(PAIR_SYSTEM, "Pairs:\n\n" + "\n".join(lines),
                                           model=settings.extract_model, max_tokens=4000)
        except gateway.GatewayError:
            continue                       # unjudged -> unsure -> keep; safe
        for o in objs:
            if isinstance(o, dict):
                v = str(o.get("verdict", "")).lower()
                if v in ("same", "distinct", "contradicts", "unsure"):
                    out[str(o.get("id"))] = v
    return out


async def reconcile_pairs(conn, *, max_pairs: int, commit: bool) -> ReconcileReport:
    rep = ReconcileReport()
    rows = await conn.fetch(
        "WITH nn AS ("
        "  SELECT a.id AS a_id, b.id AS b_id,"
        "         1 - (a.embedding <=> b.embedding) AS sim,"
        "         row_number() OVER (PARTITION BY a.id ORDER BY a.embedding <=> b.embedding) AS rn"
        "  FROM memories a JOIN memories b"
        "    ON b.id < a.id AND b.tier = a.tier AND b.retired_at IS NULL"
        "   AND b.embedding IS NOT NULL"
        "  WHERE a.retired_at IS NULL AND a.embedding IS NOT NULL"
        "    AND a.tier = ANY($1::text[])"
        ") SELECT a_id, b_id, sim FROM nn WHERE rn = 1"
        "   AND sim >= $2 AND sim < $3 ORDER BY sim DESC LIMIT $4",
        list(RECONCILE_TIERS), PAIR_FLOOR, BLIND_MERGE, max_pairs)

    pairs = []
    for r in rows:
        a = await conn.fetchrow(
            "SELECT id, fact, tier, source_key, corroboration_count, recall_count,"
            " event_at, created_at FROM memories WHERE id=$1 AND retired_at IS NULL", r["a_id"])
        b = await conn.fetchrow(
            "SELECT id, fact, tier, source_key, corroboration_count, recall_count,"
            " event_at, created_at FROM memories WHERE id=$1 AND retired_at IS NULL", r["b_id"])
        if not a or not b:
            continue
        if route(a["fact"], b["fact"]) == "distinct":
            continue
        pairs.append({"pair_id": f'{a["id"]}_{b["id"]}', "a": dict(a), "b": dict(b),
                      "fact_a": a["fact"], "fact_b": b["fact"]})
    rep.pairs_judged = len(pairs)
    if not pairs:
        return rep

    v1 = await _judge_pairs(pairs, swap=False)
    v2 = await _judge_pairs(pairs, swap=True)

    for p in pairs:
        a, b = v1.get(p["pair_id"], "unsure"), v2.get(p["pair_id"], "unsure")
        if a != b:
            continue                       # double agreement or nothing
        if a == "same":
            keep, drop = p["a"], p["b"]
            if (drop["corroboration_count"], drop["recall_count"]) > \
               (keep["corroboration_count"], keep["recall_count"]):
                keep, drop = drop, keep
            same_src = keep["source_key"] is not None and \
                keep["source_key"] == drop["source_key"]
            if commit:
                if not same_src:
                    await conn.execute(
                        "UPDATE memories SET corroboration_count = corroboration_count"
                        " + $2, updated_at=now() WHERE id=$1",
                        keep["id"], drop["corroboration_count"])
                await conn.execute(
                    "UPDATE memories SET retired_at=now(), superseded_by_id=$1,"
                    " retired_reason='reconciler: same-claim fold'"
                    " WHERE id=$2 AND retired_at IS NULL", keep["id"], drop["id"])
            rep.folded += 1
        elif a == "contradicts":
            winner, loser = pick_survivor(p["a"], p["b"])
            if commit:
                await conn.execute(
                    "UPDATE memories SET retired_at=now(), superseded_by_id=$1,"
                    " retired_reason='reconciler: contradicted by newer (M6)'"
                    " WHERE id=$2 AND retired_at IS NULL", winner["id"], loser["id"])
            rep.contradictions += 1
            rep.details.append(("contradiction", loser["id"], winner["id"],
                                loser["fact"][:70], winner["fact"][:70]))
    return rep


async def resolve_loops(conn, *, max_loops: int, commit: bool,
                        min_age_days: int = 2) -> ReconcileReport:
    rep = ReconcileReport()
    loops = await conn.fetch(
        "SELECT id, fact, created_at, embedding FROM memories"
        " WHERE retired_at IS NULL AND tier='open_loop'"
        "   AND embedding IS NOT NULL"
        "   AND created_at < now() - ($1 || ' days')::interval"
        " ORDER BY created_at LIMIT $2", str(min_age_days), max_loops)
    candidates = []
    for lp in loops:
        ev = await conn.fetch(
            "SELECT id, fact FROM memories"
            " WHERE retired_at IS NULL AND id <> $1 AND tier <> 'open_loop'"
            "   AND created_at > $2 AND embedding IS NOT NULL"
            " ORDER BY embedding <=> $3 LIMIT 4",
            lp["id"], lp["created_at"], lp["embedding"])
        if ev:
            candidates.append({"loop": dict(lp), "evidence": [dict(e) for e in ev]})
    rep.loops_checked = len(candidates)
    if not candidates:
        return rep

    B = 5
    verdicts: dict[str, tuple[str, int | None]] = {}
    for i in range(0, len(candidates), B):
        chunk = candidates[i:i + B]
        blocks = []
        for c in chunk:
            ev_lines = "\n".join(f'  [{e["id"]}] {e["fact"][:200]}' for e in c["evidence"])
            blocks.append(f'{c["loop"]["id"]}:\nOPEN LOOP: {c["loop"]["fact"][:250]}\n'
                          f'LATER MEMORIES:\n{ev_lines}\n')
        try:
            objs = await gateway.chat_json(RESOLVE_SYSTEM, "Items:\n\n" + "\n".join(blocks),
                                           model=settings.extract_model, max_tokens=3000)
        except gateway.GatewayError:
            continue
        for o in objs:
            if isinstance(o, dict) and str(o.get("resolved", "")).lower() in ("yes", "no"):
                try:
                    evid = int(o["evidence"]) if o.get("evidence") is not None else None
                except (TypeError, ValueError):
                    evid = None
                verdicts[str(o.get("id"))] = (o["resolved"].lower(), evid)

    for c in candidates:
        lid = str(c["loop"]["id"])
        verdict, evid = verdicts.get(lid, ("no", None))
        valid_ev = {e["id"] for e in c["evidence"]}
        if verdict == "yes" and evid in valid_ev:
            if commit:
                await conn.execute(
                    "UPDATE memories SET retired_at=now(), superseded_by_id=$1,"
                    " retired_reason='reconciler: loop resolved (M6)'"
                    " WHERE id=$2 AND retired_at IS NULL", evid, c["loop"]["id"])
            rep.loops_resolved += 1
            rep.details.append(("resolved", c["loop"]["id"], evid,
                                c["loop"]["fact"][:70], ""))
    return rep


async def run(conn, *, commit: bool) -> ReconcileReport:
    """One capped reconciliation pass; the dream sweeper calls this nightly."""
    total = ReconcileReport()
    if not settings.reconcile_enabled:
        return total
    pr = await reconcile_pairs(conn, max_pairs=settings.reconcile_max_pairs, commit=commit)
    lr = await resolve_loops(conn, max_loops=settings.reconcile_max_loops, commit=commit)
    total.pairs_judged = pr.pairs_judged
    total.folded = pr.folded
    total.contradictions = pr.contradictions
    total.loops_checked = lr.loops_checked
    total.loops_resolved = lr.loops_resolved
    total.details = pr.details + lr.details
    logger.info("reconciler %s: pairs=%d folded=%d contradictions=%d"
                " loops_checked=%d resolved=%d",
                "COMMIT" if commit else "dry-run", total.pairs_judged, total.folded,
                total.contradictions, total.loops_checked, total.loops_resolved)
    return total
