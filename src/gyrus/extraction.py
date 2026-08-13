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

Model: kaiju/nemotron:70b. Scale is not the lever here — the 120B lost domain
facts the 70B caught, and the flash tier extracted almost nothing (dry-run #2
and #3). Prompt design won; the big model does not.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable

from . import gateway
from .config import settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

TIERS = ("procedural", "factual", "preference", "open_loop", "knowledge")
PROVENANCE = ("ken_said", "observed", "relayed", "assistant_suggested")

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
- If the window is automated output (a scheduled job's report, a news digest)
  rather than a human exchange, extract NOTHING. Content a script produced is
  never a preference of Ken's.

Return ONLY a JSON array (no markdown fences, no prose):
[{"tier": "...", "fact": "...", "entities": ["..."], "provenance": "...", "topic": ["..."]}]
Return [] if nothing qualifies."""


@dataclass
class Fact:
    tier: str
    fact: str
    entities: list[str]
    provenance: str
    topic: list[str] = None            # knowledge-tier tags (None -> [])
    source_type: str = "conversation"  # where it came from; thalamus overrides for M5

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
        f = Fact(tier=tier, fact=fact, entities=entities, provenance=prov, topic=topic)
        if f.hash in seen:      # the model repeating itself within one window
            continue
        seen.add(f.hash)
        out.append(f)
    return out


async def extract(messages: Iterable[dict[str, Any]], *, model: str | None = None) -> list[Fact]:
    """Run one window through the extraction pass."""
    window = render_window(messages)
    if not window.strip():
        return []
    raw = await gateway.chat_json(SYSTEM, f"Conversation window:\n\n{window}", model=model)
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

    primary, secondary = await asyncio.gather(
        extract(messages),
        extract(messages, model=settings.extract_union_model) if settings.extract_union_model else _none(),
    )
    merged: dict[str, Fact] = {f.hash: f for f in primary}
    for f in secondary:
        merged.setdefault(f.hash, f)
    if len(merged) > len(primary):
        logger.info("union pass added %d facts", len(merged) - len(primary))
    return list(merged.values())


async def _none() -> list[Fact]:
    return []


async def persist(conn, facts: list[Fact], *, turn_id: int | None,
                  session_id: str | None, source_ref: str | None = None) -> int:
    """Write facts to the semantic tier, embedding and deduping as we go.

    Dedupe is two-stage: exact hash (a partial unique index does the work),
    then near-duplicate by cosine — a fact restated in different words is
    corroboration, not a new memory. Corroboration frequency IS the factual
    tier's reward signal (ADR-0002), so a duplicate is a signal, not waste.
    """
    if not facts:
        return 0
    vectors = await gateway.embed([f.fact for f in facts])
    written = 0
    for f, vec in zip(facts, vectors):
        pgvec = gateway.to_pgvector(vec)
        # near-duplicate check (only possible when both sides have vectors)
        if pgvec is not None:
            dup = await conn.fetchrow(
                "SELECT id, 1 - (embedding <=> $1::vector) AS sim FROM memories"
                " WHERE retired_at IS NULL AND tier = $2 AND embedding IS NOT NULL"
                " ORDER BY embedding <=> $1::vector LIMIT 1",
                pgvec, f.tier)
            if dup and dup["sim"] is not None and dup["sim"] >= settings.dedupe_threshold:
                await conn.execute(
                    "UPDATE memories SET corroboration_count = corroboration_count + 1,"
                    " updated_at = now() WHERE id = $1", dup["id"])
                continue
        row = await conn.fetchrow(
            "INSERT INTO memories (tier, fact, entities, provenance, embedding, fact_hash,"
            " source_turn_id, source_session_id, extractor, source_type, source_ref, topic)"
            " VALUES ($1, $2, $3, $4, $5::vector, $6, $7, $8, $9, $10, $11, $12)"
            " ON CONFLICT (fact_hash) WHERE retired_at IS NULL DO UPDATE"
            "   SET corroboration_count = memories.corroboration_count + 1, updated_at = now()"
            " RETURNING id, (xmax = 0) AS inserted",
            f.tier, f.fact, f.entities, f.provenance, pgvec, f.hash,
            turn_id, session_id, f"{settings.extract_model}:{PROMPT_VERSION}",
            f.source_type, source_ref, f.topic)
        if row and row["inserted"]:
            written += 1
            if f.entities:
                await conn.executemany(
                    "INSERT INTO memory_entities (memory_id, entity, normalized)"
                    " VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    [(row["id"], e, " ".join(e.lower().split())) for e in f.entities])
    return written
