"""The extraction pass: turns in, durable facts out. Never transcripts.

Prompt lineage (all measured in tools/extraction-eval/):
  v0   — tier taxonomy + discernment rules. 70B: 6 facts, 100% precision.
  v0.1 — + recurrence rule ("like yesterday's" makes a format request a
         PREFERENCE). 70B: 7-8 facts, still 100% precision. Champion of the
         golden-set matrix: 96% keep-rate, 0% noise.
  v1   — + 'relayed' provenance (grading 2026-08-12: Ken transcribing a
         speaker is not Ken asserting), + explicit reference-capture rule
         (the graded recall gaps were ALL entity/reference-class: contact
         emails, a library name, a speaker attribution).
  v1.1 — + source-document rule (github lane 2026-08-14: markdown TOC/link
         lists extracted as "facts"; noise 1.6% -> 0.3% after the rule).
  v1.2 — + email-newsletter rule (email lane 2026-08-15: skip sponsor blocks,
         unsubscribe footers, polls; extract article claims as relayed).
  v1.3 — 2026-08-16, three rules from the store audit (journal-020/023):
         (1) knowledge/factual boundary sharpened ("would it be true if Ken
         never existed?") — v1.2 misfiled ~20% of non-cron facts;
         (2) automated-output recognition by SHAPE (standing job instruction +
         report addressed to no one -> []) — cron windows extracted 6/4 facts
         under v1.2 where the right answer is 0;
         (3) ADR-0011 "expires" field on explicitly time-scoped facts
         (day/week/month -> valid_until via EXPIRES_DAYS).

Model: the lab/extract shape (ADR-0012), bound to nemotron:70b on kaiju as of
ADR-0010 — chosen on deliverability and contract adherence, measured on six
golden windows. (An older line here claimed "the 120B lost domain facts the
70B caught" — discredited, one window on the v0 prompt; see ADR-0010.)

Going the other way is measured too, as of 2026-08-15: the fast lane
(lab/flash == vllm/nemotron-lightning-l4, one backend under two names) is
1.9x end-to-end, NOT the 9x its tok/s suggests — these windows are long-input
and short-output, so wall-clock is prefill-bound and decode throughput barely
shows. It also drops the JSON contract on 2 of 6 golden windows and files
world knowledge as `procedural`, which is the one tier ADR-0002 makes
falsifiable. Not a candidate. The older claim here ("the flash tier extracted
almost nothing") was a misconfiguration — a 403 model id — recorded as a
quality verdict; see ADR-0010.

CAVEAT on the historical numbers above: the v0/v0.1/v1 figures come from
tools/extraction-eval/run_matrix.py, whose `\\[.*\\]` regex silently scored
real model output as zero facts. Treat them as lineage narrative, not data.

v1.2 VERIFIED 2026-08-16 under bench_lanes.py (lab/extract, 6 goldens,
max_tokens=8000): 6/6 windows usable, 37 facts, 192.8s — matching ADR-0010's
engine-level run through the new shape name. Graded fact-by-fact:
  - non-cron windows (27 facts): 0 structural noise, ~93% keep-rate — the
    old "96%, 0% noise" claim roughly survives on the honest instrument;
  - BUT ~20% of non-cron facts file relayed world knowledge as 'factual'
    (e.g. a research center's existence) — the store-audit wrong-tier defect
    is live prompt behavior, not just pre-ADR-0006 backlog. Until the prompt
    learns the knowledge tier boundary, the re-tier sweep
    (tools/store-audit/retier_classify.py) needs to be periodic;
  - cron windows still extract (6 and 4 facts where the right answer is 0) —
    the suppression defect in TASKS.md, unchanged, worker filter still the
    only guard.

v1.3 VERIFIED 2026-08-16, same instrument (journal-024): 6/6 windows, 30
facts. Cron windows now return [] on both goldens (the working tell:
automated output usually SAYS it is automated — cron mentions, skill-dump
user messages). Non-cron wrong-tier fell from ~20% to ~0-3% (conference
world facts now knowledge|relayed). The model ignores the "expires" field
even with a verbatim example, so _clean() infers expiry deterministically
on open_loop/preference from the fact's own words — deterministic beats
persuasive, same lesson as the cron guards.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from . import gateway
from .config import settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.3"

TIERS = ("procedural", "factual", "preference", "open_loop", "knowledge")
PROVENANCE = ("ken_said", "observed", "relayed", "assistant_suggested")
# ADR-0011: the model's expiry classes -> how long the fact stays live.
# Coarse on purpose — the model only sees the words ("tonight", "this week");
# pretending finer resolution would be fiction.
EXPIRES_DAYS = {"day": 2, "week": 9, "month": 35}

SYSTEM = """You are the extraction pass of a personal AI agent's long-term memory system. \
The agent (Pip) serves one user, Ken. You receive a window of a real conversation and \
extract ONLY durable memories — things worth knowing 30+ days from now.

Classify each memory into exactly one tier:
- "procedural": a method, command, workflow, script, or configuration that worked or failed
- "factual": stable facts about the world, people, organizations, projects, events
- "preference": how Ken likes to work, communicate, or be helped
- "open_loop": an unresolved commitment, question, or follow-up either party owes
- "knowledge": external/world knowledge Ken is deliberately gathering, NOT a fact
  about Ken himself — a conference talk's content, a paper's finding, a podcast's
  argument, an industry/technical fact he's tracking. Give it a "topic" (1-3
  short tags) and, if named, the source.

THE GATE (decide personal vs knowledge first): is Ken teaching me about HIMSELF,
his work, or his preferences (-> procedural/factual/preference/open_loop), or is
Ken recording the WORLD he's tracking (-> knowledge)? "Ken's vault path is X" is
personal-factual; "RIKEN's ROQUO is a GPU-quantum supercomputer" is knowledge.
When Ken transcribes a talk or forwards a paper, its content is knowledge
(provenance "relayed"), not a fact about Ken.
The test: WOULD THE SENTENCE STILL BE TRUE IF KEN HAD NEVER EXISTED? Then it is
"knowledge", never "factual". Institutional and organizational facts — a
research center exists at a lab, a company's product or roadmap, a program's
structure, who runs or collaborates on what — are "knowledge" unless Ken is a
member of them or they are his own projects. "Q-NEXT is a research center at
Argonne" is knowledge; "Ken's dell-vendor-intel project maps vendors to
categories" is factual. Reserve "factual" for facts ABOUT Ken's world: his
projects, systems, colleagues, employer, commitments.
This holds even when Ken himself is the one typing: in conference or talk
notes, the sessions, speakers, their claims, vendor products, papers, arXiv
ids, and URLs are ALL "knowledge" with provenance "relayed" — Ken writing
"Microsoft Azure has a Resource Estimator" into his notes does not make it a
fact about Ken. The only personal facts in a conference window are Ken's own
actions, contacts made, and follow-ups owed.

Label how the memory is known (provenance):
- "ken_said": Ken asserted it about himself, his work, or his preferences
- "relayed": Ken is transcribing or reporting someone else's claim (a conference
  speaker, a paper, a colleague). The CONTENT is theirs, not Ken's — say whose.
- "observed": evident from the exchange itself rather than stated
- "assistant_suggested": the assistant proposed it and Ken did not confirm

Discernment rules (the whole point — most of the conversation is NOT memory):
- SKIP pleasantries, one-off logistics, and formatting requests bound to this
  single task — UNLESS the request references a prior instance or a repeating
  pattern ("like yesterday's", "same deal as", "same format as last time",
  "again"): a format asked for repeatedly is a PREFERENCE being expressed;
  extract it as one.
- SKIP anything inside a [CONTEXT COMPACTION] block (background, not new).
- CAPTURE named references Ken will want to find again: tools and libraries
  with versions, paper/arXiv identifiers, URLs, contact addresses, and WHO gave
  a talk or made a claim. These are cheap to store and expensive to re-find.
- Each fact must be ATOMIC (one claim), SELF-CONTAINED (explicit names, never
  pronouns or "the above"), and GROUNDED in the window (no outside knowledge,
  no embellishment, no inference beyond what was said).
- Deduplicate: repeated or duplicated messages yield one memory, not two.
- If the window is automated output rather than a human exchange, extract
  NOTHING — return []. Recognize automated output by its SHAPE, not its topic:
  the "user" message is a standing job instruction or template (a scheduled
  brief, a "weekly questions" job, a radar/digest/monitor prompt, a cron task
  describing its own schedule), and the "assistant" message is a formatted
  report addressed to no one, with no human back-and-forth. Two more tells,
  each sufficient on its own: (a) ANY text in the window saying the exchange
  is a scheduled or automated run — "cron", "scheduled job", "when running as
  a scheduled task", "this brief was generated" — means return [], full stop;
  (b) a "user" message that is a pasted skill definition, command file, or
  instruction block (frontmatter, "# Skill", "[IMPORTANT: the user has
  invoked...]") with no spontaneous human question attached is a job harness,
  not a person. When any tell is present the correct output is [] EVEN IF the
  report contains true and interesting facts — a scheduled job restating
  facts is not Ken saying them, and a job's own instructions are not Ken's
  preferences. If you are unsure whether a window is automated, ask: did a
  human write anything in it spontaneously? If not, return [].
- When the window is a SOURCE DOCUMENT (a README, journal entry, or notes file,
  usually marked with a [Source: ...] header) rather than a live exchange,
  extract the durable CLAIMS it makes — findings, decisions, metrics, facts —
  and SKIP its scaffolding: tables of contents, "related documents"/"see also"
  link lists, navigation, file/section listings, and any description of the
  document system itself ("has entries like journey-27", "related docs include
  adr/0004"). A list of document or section names is never a memory.
- When the source document is an EMAIL NEWSLETTER, extract the claims of its
  articles — announcements, findings, metrics, arguments, WHO shipped/said WHAT —
  as knowledge with provenance "relayed", crediting the newsletter as the source.
  SKIP its chrome: header navigation, sponsor/"in partnership with" ad blocks,
  subscribe/unsubscribe boilerplate, privacy/legal footers, referral and job-board
  CTAs, reader polls, social links, and any garbled or decorative text. Read-time
  estimates and section headers are not memories.

- If a fact's own words scope it in time — "tonight", "today", "next session",
  "this week", "by Monday", "this month" — it is usually NOT durable: skip it
  unless it is a real open_loop, or a durable fact/preference underneath the
  scope. When you do extract a time-scoped fact, add an "expires" field:
  "day" (tonight / today / next session), "week" (this week / by a weekday),
  or "month" (this month / this quarter). Example: "Verify the delivery
  process on Monday" -> {"tier": "open_loop", ..., "expires": "week"}. An
  open_loop with a stated deadline should ALWAYS carry expires. Facts with no
  stated time scope must OMIT the field — never guess an expiry.

Return ONLY a JSON array (no markdown fences, no prose):
[{"tier": "...", "fact": "...", "entities": ["..."], "provenance": "...", "topic": ["..."], "expires": "day|week|month — ONLY when the fact is explicitly time-scoped"}]
Return [] if nothing qualifies."""


@dataclass
class Fact:
    tier: str
    fact: str
    entities: list[str]
    provenance: str
    topic: list[str] = None            # knowledge-tier tags (None -> [])
    source_type: str = "conversation"  # where it came from; thalamus overrides for M5
    # ADR-0011: the model flags explicitly time-scoped facts ("tonight",
    # "this week") with an expiry class; persist() turns it into valid_until.
    expires: str | None = None         # "day" | "week" | "month" | None
    # When the fact was true/observed. Set by the INGEST path from the source
    # item's published_at (message date, arXiv submission, commit date) —
    # never by the model, which has no calendar. None = unknown (created_at).
    event_at: datetime | None = None

    def __post_init__(self):
        if self.topic is None:
            self.topic = []

    @property
    def hash(self) -> str:
        norm = " ".join(self.fact.lower().split())
        return hashlib.sha256(norm.encode()).hexdigest()[:32]


def render_window(messages: Iterable[dict[str, Any]], *, char_budget: int | None = None) -> str:
    """Flatten a message window for the prompt, inside a character budget.

    Whole sessions are never fed to the model — the two longest conference
    windows in the golden set blew past serving contexts (measured). Callers
    chunk; this only enforces the ceiling.
    """
    budget = char_budget or settings.extract_char_budget
    parts = []
    for m in messages:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"[{str(m.get('role', 'user')).upper()}]\n{content}")
    text = "\n\n".join(parts)
    if len(text) > budget:
        text = text[:budget] + "\n\n[WINDOW TRUNCATED FOR CONTEXT BUDGET]"
    return text


_EXPIRY_PATTERNS = (
    (r"\b(tonight|this evening|later today|next session|by tomorrow|tomorrow morning)\b", "day"),
    (r"\b(this week|by (mon|tues|wednes|thurs|fri|satur|sun)day|on (mon|tues|wednes|thurs|fri|satur|sun)day|by end of (the )?week|next week)\b", "week"),
    (r"\b(this month|this quarter|by end of (the )?month)\b", "month"),
)


def _infer_expiry(fact: str) -> str | None:
    """ADR-0011 backstop: read the time scope the fact's own words state.
    Conservative on purpose — bare 'today' is excluded (too often rhetorical),
    and no match means durable, never a guess."""
    low = fact.lower()
    for pat, cls in _EXPIRY_PATTERNS:
        if re.search(pat, low):
            return cls
    return None


def _clean(raw: list[dict[str, Any]]) -> list[Fact]:
    """Validate and normalize model output. Anything malformed is dropped."""
    out: list[Fact] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        tier = str(item.get("tier", "")).strip().lower()
        fact = " ".join(str(item.get("fact", "")).split())
        if tier not in TIERS or len(fact) < 8:
            continue
        prov = str(item.get("provenance", "observed")).strip().lower()
        if prov not in PROVENANCE:
            prov = "observed"
        ents = item.get("entities") or []
        entities = [" ".join(str(e).split()) for e in ents if str(e).strip()][:24]
        tops = item.get("topic") or []
        topic = [" ".join(str(t).split()).lower() for t in tops if str(t).strip()][:6]
        expires = str(item.get("expires", "")).strip().lower() or None
        if expires not in EXPIRES_DAYS:            # anything unrecognized -> durable
            expires = None
        if expires is None and tier in ("open_loop", "preference"):
            # The golden-set pass showed the model ignoring the expires field
            # even with a verbatim example (v1.3 bench, 2026-08-16), so the
            # prompt rule gets a deterministic backstop — same lesson as the
            # cron guard. Only on the tiers where frozen ephemera do damage:
            # a knowledge claim saying "today" is usually rhetoric, but an
            # open_loop "by Monday" or a preference "tonight" has a real clock.
            expires = _infer_expiry(fact)
        f = Fact(tier=tier, fact=fact, entities=entities, provenance=prov, topic=topic,
                 expires=expires)
        if f.hash in seen:      # the model repeating itself within one window
            continue
        seen.add(f.hash)
        out.append(f)
    return out


async def extract(messages: Iterable[dict[str, Any]], *, model: str | None = None,
                  max_tokens: int | None = None,
                  timeout: float | None = None,
                  template_kwargs: dict[str, Any] | None = None) -> list[Fact]:
    """Run one window through the extraction pass.

    max_tokens is exposed for the lane bench: a THINKING model spends the
    budget reasoning before it writes, so measuring one at the default is
    measuring its budget, not its extraction. Three of the 120B's golden-set
    runs in dry-run #3 read "thinking ate budget" / "truncated JSON" and were
    recorded as quality results (ADR-0010).

    timeout is exposed for the same reason, one layer down. chat_json's 300s
    ceiling is only lifted for the configured fallback model, and the bench
    blanks the fallback so each lane answers for itself — so a slow lane under
    test got 300s no matter what settings.extract_fallback_timeout said. A
    lane that cannot finish inside the ceiling scores as a quality failure
    when it is really a clock failure, which is the exact confusion ADR-0010
    was written to correct.
    """
    window = render_window(messages)
    if not window.strip():
        return []
    kw: dict[str, Any] = {"max_tokens": max_tokens} if max_tokens else {}
    if timeout:
        kw["timeout"] = timeout
    if template_kwargs:
        kw["template_kwargs"] = template_kwargs
    raw = await gateway.chat_json(SYSTEM, f"Conversation window:\n\n{window}",
                                  model=model, **kw)
    facts = _clean(raw)
    logger.info("extracted %d facts (%d chars in)", len(facts), len(window))
    return facts


async def extract_union(messages: Iterable[dict[str, Any]]) -> list[Fact]:
    """Primary extractor + a cheap second pass, merged.

    Grading showed every recall gap was entity/reference-class — contact
    addresses, a library name, a speaker attribution — and that a different
    model caught exactly those while missing the domain facts. Two passes
    cost nothing on idle local silicon and cover each other's blind spots.
    """
    import asyncio

    # The second opinion is a BONUS pass, so its lane being down must not fail
    # the window — but the primary's silence must propagate (GatewayError), or
    # the caller stamps the turn extracted having learned nothing. See
    # gateway.chat_json.
    primary, secondary = await asyncio.gather(
        extract(messages),
        extract(messages, model=settings.extract_union_model) if settings.extract_union_model else _none(),
        return_exceptions=True,
    )
    if isinstance(primary, BaseException):
        raise primary
    if isinstance(secondary, BaseException):
        logger.warning("union pass unavailable (%s); continuing on the primary alone",
                       secondary)
        secondary = []
    merged: dict[str, Fact] = {f.hash: f for f in primary}
    for f in secondary:
        merged.setdefault(f.hash, f)
    if len(merged) > len(primary):
        logger.info("union pass added %d facts", len(merged) - len(primary))
    return list(merged.values())


async def _none() -> list[Fact]:
    return []


async def persist(conn, facts: list[Fact], *, turn_id: int | None,
                  session_id: str | None, source_ref: str | None = None,
                  source_key: str | None = None) -> int:
    """Write facts to the semantic tier, embedding and deduping as we go.

    Dedupe is two-stage: exact hash (a partial unique index does the work),
    then near-duplicate by cosine — a fact restated in different words is
    corroboration, not a new memory. Corroboration frequency IS the factual
    tier's reward signal (ADR-0002), so a duplicate is a signal, not waste.

    BUT corroboration requires INDEPENDENCE. A newsletter's templated footer
    recurs in every issue; folding each recurrence into corroboration let a
    legal-footer "fact" reach 29x from one source talking to itself (measured
    2026-08-15, email backfill). source_key names the canonical origin
    (newsletter, repo, paper); a near-dup from the SAME source_key is dropped
    without a bump. None (conversation path) keeps the original behaviour.

    Corroboration bumps are COLLECTED and applied once at the end, in id
    order. Applied inline they were a deadlock generator: two concurrent
    windows over the same session hit the same duplicates in different orders
    and each held row locks for the rest of its transaction, so Postgres shot
    one of them (measured 2026-08-15 — `DeadlockDetectedError` at 2 parallel
    windows, which is also `extract_concurrency`'s default, so the live worker
    could hit it too). One sorted statement means every writer takes these
    locks in the same order and holds them for the shortest possible time.
    """
    if not facts:
        return 0
    vectors = await gateway.embed([f.fact for f in facts])
    # No vector means the near-duplicate check below cannot run, and a fact
    # inserted unchecked looks deduped forever once the sweeper backfills its
    # embedding (audit brief 2026-08-15 #9; measured footprint: turn 823,
    # journal-021). Ken's ruling: the WRITE path fails loudly and lets the
    # caller retry (worker leaves extracted_at NULL, /v1/extract-window 503s,
    # ingest holds its cursor) rather than insert undeduped. embed()'s
    # None-tolerance is for the RETRIEVAL path, which degrades to two legs —
    # that behaviour is deliberate and unchanged.
    if any(v is None for v in vectors):
        raise gateway.GatewayError(
            f"embedder unavailable; refusing to persist {len(facts)} facts undeduped")
    written = 0
    corroborate: dict[int, int] = {}       # memory id -> how many times bumped
    fresh: set[int] = set()                # inserted by THIS call
    # Hash order, so concurrent writers attempt the exact-hash upsert below in
    # the same sequence. The batched bump at the end fixed lock ordering for
    # the cosine path; ON CONFLICT DO UPDATE takes a row lock too, and left
    # unordered it could still deadlock two windows extracting the same facts.
    for f, vec in sorted(zip(facts, vectors), key=lambda fv: fv[0].hash):
        pgvec = gateway.to_pgvector(vec)
        # near-duplicate check (only possible when both sides have vectors)
        if pgvec is not None:
            dup = await conn.fetchrow(
                "SELECT id, source_key, 1 - (embedding <=> $1::vector) AS sim FROM memories"
                " WHERE retired_at IS NULL AND tier = $2 AND embedding IS NOT NULL"
                " ORDER BY embedding <=> $1::vector LIMIT 1",
                pgvec, f.tier)
            if dup and dup["sim"] is not None and dup["sim"] >= settings.dedupe_threshold:
                # Counted, not just flagged: two facts in one window can land
                # on the same memory, and that is two corroborations — unless
                # the duplicate is the same source repeating itself.
                #
                # `fresh` is that same independence rule for the CONVERSATION
                # path, where source_key is always None so the check above
                # never fires. Without it a window that states a fact twice
                # inserts it once and then corroborates it with its own
                # restatement — one utterance voting twice, on the tiers where
                # ADR-0002 actually depends on the signal.
                same_source = source_key is not None and dup["source_key"] == source_key
                if not same_source and dup["id"] not in fresh:
                    corroborate[dup["id"]] = corroborate.get(dup["id"], 0) + 1
                continue
        # ADR-0011: an explicitly time-scoped fact carries its expiry; the
        # dream pass retires it once valid_until passes. event_at comes from
        # the source item (ingest path) and is NULL for live conversation.
        valid_until = None
        if f.expires in EXPIRES_DAYS:
            valid_until = datetime.now(timezone.utc) + timedelta(days=EXPIRES_DAYS[f.expires])
        row = await conn.fetchrow(
            "INSERT INTO memories (tier, fact, entities, provenance, embedding, fact_hash,"
            " source_turn_id, source_session_id, extractor, source_type, source_ref, topic,"
            " source_key, event_at, valid_until)"
            " VALUES ($1, $2, $3, $4, $5::vector, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)"
            # The exact-hash bump honours the same independence rule as the
            # cosine path (migration 0006): a source re-serving its own
            # sentence verbatim — an edited github doc re-crossing with its
            # unchanged paragraphs (thalamus content-hash change, 2026-08-16)
            # — is repetition, not corroboration. Cross-source exact matches
            # still count.
            " ON CONFLICT (fact_hash) WHERE retired_at IS NULL DO UPDATE"
            "   SET corroboration_count = memories.corroboration_count"
            "     + CASE WHEN memories.source_key IS NOT NULL"
            "             AND memories.source_key = EXCLUDED.source_key"
            "            THEN 0 ELSE 1 END,"
            "       updated_at = now()"
            " RETURNING id, (xmax = 0) AS inserted",
            f.tier, f.fact, f.entities, f.provenance, pgvec, f.hash,
            turn_id, session_id, f"{settings.extract_model}:{PROMPT_VERSION}",
            f.source_type, source_ref, f.topic, source_key, f.event_at, valid_until)
        if row and row["inserted"]:
            written += 1
            fresh.add(row["id"])
            if f.entities:
                await conn.executemany(
                    "INSERT INTO memory_entities (memory_id, entity, normalized)"
                    " VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    [(row["id"], e, " ".join(e.lower().split())) for e in f.entities])
    if corroborate:
        # Sorted ids = a global lock order every writer agrees on, so two
        # windows bumping the same memories can no longer deadlock.
        ids = sorted(corroborate)
        await conn.execute(
            "UPDATE memories m SET corroboration_count = m.corroboration_count + v.n,"
            " updated_at = now() FROM (SELECT unnest($1::bigint[]) AS id,"
            " unnest($2::int[]) AS n) v WHERE m.id = v.id",
            ids, [corroborate[i] for i in ids])
    return written
