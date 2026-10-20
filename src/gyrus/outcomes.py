"""M3 — the outcome-signal writer. The procedural tier's evaluator.

This is the one piece the module-lift map marks REPLACE-per-tier: the credit
engine (gemma-forge) consumes `outcome_value` / `followed_*` from a retrievals
table; THIS produces them for gyrus's procedural tier. Everything downstream
(credit assignment in the dream pass) ports unchanged once these columns are fed.

The signal, derived from a completed turn's own message list (which the provider
ships verbatim — tool calls and results included):

  1. Did a recalled procedural memory get FOLLOWED? — embedding similarity
     between the memory's fact and what the agent actually did (its tool-call
     args + assistant text). gemma-forge's `tip_followed_emb`, domain-agnostic.
     An LLM judge (temp 0) can be layered on later; the embedding leg alone is
     the cheap, deterministic first cut.
  2. Did the tools SUCCEED? — parsed from the turn's tool-result messages.
  3. Graded outcome — followed + succeeded = +1.0; followed + failed = -0.3
     (the tip's advice was taken and didn't work); not-followed = no signal
     about that memory (skip). Same graded shape as gemma-forge's evaluator.

Offline only: scored after the turn, never on the turn path.
"""

from __future__ import annotations

import json
import logging
import re

from . import db, gateway
from .extraction import content_text
from .config import settings

logger = logging.getLogger(__name__)

FOLLOW_EMB_THRESHOLD = 0.55     # cosine(memory, action) at/above = followed
OUTCOME_FOLLOWED_OK = 1.0
OUTCOME_FOLLOWED_FAIL = -0.3
OUTCOME_CONFIDENCE = 0.8        # embedding-only
OUTCOME_CONFIDENCE_LLM = 0.95   # embedding + LLM judge agree
RETRY_WINDOW = 3                # a failed tool re-called within this many calls = retry

# M3's "LLM tip_followed judge (temp 0)" — the second leg the module docstring
# promised. Runs ONLY on candidates the embedding leg already flagged as
# followed: cosine similarity says "the action is near this memory", the judge
# answers the sharper question "did the action actually APPLY it?". Agreement
# raises outcome confidence; refutation corrects an embedding false-positive
# to not-followed (similar wording, different deed — the confidently-wrong
# case ADR-0002 warns about). Judge unavailable -> embedding verdict stands at
# its own confidence; the leg is an upgrade, never a dependency.
FOLLOW_JUDGE_SYSTEM = """You judge whether an AI agent's actions FOLLOWED a \
remembered tip. The tip is a procedural memory (a command, workflow, or \
configuration). The action log shows what the agent actually did (its tool \
calls and text). Answer "yes" only if the action concretely applies what the \
tip describes — same command/script/approach, not merely the same topic.
Return ONLY a JSON array: [{"followed": "yes"|"no"}]"""


async def judge_followed(fact: str, action: str) -> bool | None:
    """True/False from the LLM leg; None when the judge can't answer."""
    try:
        objs = await gateway.chat_json(
            FOLLOW_JUDGE_SYSTEM,
            f"Tip:\n{fact}\n\nAction log:\n{action[:4000]}",
            model=settings.outcome_judge_model, max_tokens=500, fallback=False)
    except gateway.GatewayError:
        return None
    for o in objs:
        if isinstance(o, dict) and str(o.get("followed", "")).lower() in ("yes", "no"):
            return o["followed"].lower() == "yes"
    return None

_FAIL_MARKERS = re.compile(
    r'"success"\s*:\s*false|"error"|traceback|can\'t open|no such file|'
    r'command not found|not found|permission denied|exit code [1-9]|failed',
    re.IGNORECASE)
_OK_MARKERS = re.compile(r'"success"\s*:\s*true', re.IGNORECASE)


def tool_outcome(messages: list[dict]) -> tuple[int, int]:
    """(successes, failures) across a turn's tool-result messages."""
    ok, fail, _ = tool_outcome_detail(messages)
    return ok, fail


def tool_outcome_detail(messages: list[dict]) -> tuple[int, int, int]:
    """(successes, failures, retries) for a turn.

    A RETRY is a tool failing and the same tool being called again later in
    the turn — the observable cost of missing or wrong memory even when the
    turn ends in success (ADR-0014). Tool names come from the assistant's
    tool_calls (id -> function.name); a tool result whose id is unknown is
    counted under '?' so it can still pair with a later unknown.
    """
    names: dict[str, str] = {}
    seq: list[tuple[str, bool]] = []      # (tool name, ok) in turn order
    ok = fail = 0
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = (tc.get("function") or {})
                if tc.get("id"):
                    names[str(tc["id"])] = str(fn.get("name") or "?")
            continue
        if m.get("role") != "tool":
            continue
        content = content_text(m.get("content"))
        good = bool(_OK_MARKERS.search(content)) or not _FAIL_MARKERS.search(content)
        ok += good
        fail += not good
        seq.append((names.get(str(m.get("tool_call_id") or ""), "?"), good))
    # Same tool within the next RETRY_WINDOW calls: a 75-call turn with one
    # early terminal failure is not 74 retries (first cut over-counted —
    # 5,725 "retries" across 1,600 historical turns).
    retries = 0
    for i, (name, good) in enumerate(seq):
        if not good and any(n == name for n, _ in seq[i + 1:i + 1 + RETRY_WINDOW]):
            retries += 1
    return ok, fail, retries


def action_text(messages: list[dict]) -> str:
    """What the agent actually DID this turn — assistant text + tool-call args.

    This is the tip↔approach comparison target: gemma-forge judged the tip
    against the worker's fix_script, not its narrative. Here the equivalent is
    the concrete tool-call arguments (the commands run), plus assistant prose.
    """
    parts = []
    for m in messages:
        if m.get("role") == "assistant":
            text = content_text(m.get("content"))
            if text:
                parts.append(text)
            for tc in m.get("tool_calls") or []:
                fn = (tc.get("function") or {})
                parts.append(f"{fn.get('name', '')} {fn.get('arguments', '')}")
    return "\n".join(p for p in parts if p)[:6000]


async def score_turn(conn, turn_id: int) -> dict:
    """Write procedural outcomes for one completed turn. Returns a summary."""
    turn = await conn.fetchrow(
        "SELECT id, session_id, messages FROM episodic_turns WHERE id=$1", turn_id)

    async def _done(reason: str) -> dict:
        # Review C2 (2026-10-20): an early return used to leave the turn's
        # rows pending forever, and score_pending's unordered LIMIT 200 would
        # eventually return only such dead turns — the thesis signal stopping
        # a second time, with turns_failed: 0. Every exit stamps.
        await conn.execute(
            "UPDATE memory_retrievals SET followed_llm=false, followed_computed_at=now()"
            " WHERE turn_id=$1 AND followed_computed_at IS NULL", turn_id)
        return {"turn_id": turn_id, "scored": 0, "reason": reason}

    if not turn or not turn["messages"]:
        return await _done("no messages")
    messages = turn["messages"] if isinstance(turn["messages"], list) \
        else json.loads(turn["messages"])

    ok, fail, retries = tool_outcome_detail(messages)
    if ok + fail == 0:
        return await _done("no tool activity")
    success_rate = ok / (ok + fail)

    # ADR-0014: withheld rows were never shown, so they carry no follow
    # signal. Stamp them out of the queue before looking at the served ones.
    await conn.execute(
        "UPDATE memory_retrievals SET followed_llm=false, followed_computed_at=now()"
        " WHERE turn_id=$1 AND withheld AND followed_computed_at IS NULL", turn_id)

    # Procedural memories recalled for this turn, still unscored.
    recalls = await conn.fetch(
        "SELECT r.id, r.memory_id, m.fact, m.embedding IS NOT NULL AS has_vec"
        " FROM memory_retrievals r JOIN memories m ON m.id = r.memory_id"
        " WHERE r.turn_id=$1 AND m.tier='procedural' AND NOT r.withheld"
        "   AND r.followed_computed_at IS NULL", turn_id)
    if not recalls:
        return await _done("no unscored procedural recalls")

    act = action_text(messages)
    act_vec = gateway.to_pgvector((await gateway.embed([act]))[0]) if act else None

    scored = 0
    for r in recalls:
        followed_emb = None
        if act_vec is not None and r["has_vec"]:
            followed_emb = await conn.fetchval(
                "SELECT 1 - (embedding <=> $1::vector) FROM memories WHERE id=$2",
                act_vec, r["memory_id"])
        followed = followed_emb is not None and followed_emb >= FOLLOW_EMB_THRESHOLD
        confidence = OUTCOME_CONFIDENCE
        if followed and settings.outcome_llm_judge:
            verdict = await judge_followed(r["fact"], act)
            if verdict is True:
                confidence = OUTCOME_CONFIDENCE_LLM
            else:
                # False: embedding false-positive, corrected. None: the judge
                # could not answer — and the embedding leg alone sits below
                # the noise floor (61% of all scored rows clear 0.55, review
                # C4), so an unjudged "followed" is not evidence. No credit.
                followed = False
        if not followed:
            # No evidence this memory drove the action → no outcome signal about it.
            await conn.execute(
                "UPDATE memory_retrievals SET followed_llm=false,"
                " followed_emb=$2, followed_computed_at=now()"
                " WHERE id=$1", r["id"], followed_emb)
            continue
        value = OUTCOME_FOLLOWED_OK if success_rate >= 0.5 else OUTCOME_FOLLOWED_FAIL
        await conn.execute(
            "UPDATE memory_retrievals SET outcome_value=$2, outcome_confidence=$3,"
            " followed_emb=$4, followed_llm=$5, followed_computed_at=now() WHERE id=$1",
            r["id"], value, confidence, followed_emb,
            confidence == OUTCOME_CONFIDENCE_LLM)
        scored += 1
    logger.info("outcomes turn %s: tools %d/%d ok, %d retries, %d procedural recalls scored",
                turn_id, ok, ok + fail, retries, scored)
    return {"turn_id": turn_id, "scored": scored, "tool_ok": ok, "tool_fail": fail,
            "retries": retries, "success_rate": round(success_rate, 2),
            "recalls": len(recalls)}


async def record_turn_outcomes(limit: int = 200) -> dict:
    """ADR-0014: every completed, non-cron turn gets its tool outcome written
    to meta->'outcome' = {ok, fail, retries, served, withheld}, whether or
    not a procedural memory was involved. This is the control comparison's
    denominator; score_pending only sees turns with procedural recalls.
    `served`/`withheld` count the retrieval rows linked to the turn.
    """
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT id, messages,"
        "  (SELECT count(*) FROM memory_retrievals r WHERE r.turn_id=t.id AND NOT r.withheld) AS served,"
        "  (SELECT count(*) FROM memory_retrievals r WHERE r.turn_id=t.id AND r.withheld) AS withheld"
        " FROM episodic_turns t"
        " WHERE (meta->'outcome') IS NULL AND created_at < now() - interval '5 minutes'"
        "   AND COALESCE(platform, '') <> 'cron'"
        " ORDER BY id DESC LIMIT $1", limit)
    written = 0
    async with pool.acquire() as conn:
        for t in rows:
            msgs = t["messages"]
            if isinstance(msgs, str):
                try:
                    msgs = json.loads(msgs)
                except json.JSONDecodeError:
                    msgs = []
            ok, fail, retries = tool_outcome_detail(msgs or [])
            outcome = {"ok": ok, "fail": fail, "retries": retries,
                       "served": t["served"], "withheld": t["withheld"]}
            await conn.execute(
                "UPDATE episodic_turns SET meta = COALESCE(meta, '{}'::jsonb)"
                " || jsonb_build_object('outcome', $2::jsonb) WHERE id=$1",
                t["id"], json.dumps(outcome))
            written += 1
    return {"turns": len(rows), "written": written}


async def link_retrievals(conn, turn_id: int, session_id: str) -> int:
    """Attach a turn's id to the retrievals recalled for it.

    prefetch logs retrievals before the turn exists (no turn_id); the turn
    arrives after. So on turn write, claim the session's still-unlinked
    retrievals for this turn — the gemma-forge update_retrieval_attempt_ids
    pattern. Later turns claim only what's since accumulated.
    """
    return await conn.fetchval(
        "WITH upd AS (UPDATE memory_retrievals SET turn_id=$1"
        " WHERE session_id=$2 AND turn_id IS NULL RETURNING 1)"
        " SELECT count(*) FROM upd", turn_id, session_id)


async def score_pending(limit: int = 200) -> dict:
    """Score every turn that has tool activity and unscored procedural recalls."""
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT r.turn_id FROM memory_retrievals r"
        " JOIN memories m ON m.id=r.memory_id"
        " WHERE r.turn_id IS NOT NULL AND m.tier='procedural'"
        "   AND r.followed_computed_at IS NULL"
        " ORDER BY r.turn_id DESC LIMIT $1", limit)
    total = failed = 0
    async with pool.acquire() as conn:
        for row in rows:
            # One turn's failure is one turn's loss, never the pass's: a single
            # unscoreable turn at the head of this queue silenced outcome
            # scoring for seven weeks (2026-09-01..10-19), because the
            # exception left the loop and the same turn came first next time.
            try:
                res = await score_turn(conn, row["turn_id"])
            except Exception:                               # noqa: BLE001
                failed += 1
                logger.exception("outcome scoring failed for turn %s; skipping it this pass",
                                 row["turn_id"])
                continue
            total += res.get("scored", 0)
    return {"turns": len(rows), "outcomes_written": total, "turns_failed": failed}
