"""The only door to inference (non-negotiable #5): the LiteLLM gateway.

Chat for extraction, embeddings for the semantic leg of retrieval. Both are
async, both retry, and both fall back to a second model where a fallback is
meaningful — lab lanes are batch-claimed and come and go (measured
2026-08-11: the qwen lane vanished mid-eval when another session claimed the
GPU).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Sequence

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def salvage_objects(text: str) -> list[dict[str, Any]]:
    """Parse a JSON array of objects, tolerating malformed members.

    Whole-array parse first; on failure, walk balanced braces and parse each
    object independently. One bad object then costs ONE fact instead of the
    whole window — measured 2026-08-12: a single unescaped quote from the 70B
    silently discarded an entire conference window's extractions. (Same
    balanced-brace tolerance as gemma-forge's reflector_parser, for the same
    reason: models emit almost-JSON, and the pass must not be all-or-nothing.)
    """
    m = _JSON_ARRAY.search(text)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    out: list[dict[str, Any]] = []
    depth = start = 0
    in_str = escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        out.append(obj)
                except json.JSONDecodeError:
                    logger.debug("dropped one malformed object at %d", start)
            elif depth < 0:
                depth = 0
    return out


class GatewayError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.litellm_api_key}",
            "Content-Type": "application/json"}


async def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 4000,
    timeout: float = 300.0,
) -> list[dict[str, Any]]:
    """Chat completion whose answer is a JSON array.

    Tolerant parsing on purpose: every model in the lab wraps JSON differently
    (fences, prose preamble, a thinking block), and an extraction pass that
    throws on formatting noise would drop real facts. A malformed reply costs
    us one window, logged — never an exception into the caller.

    But a model that ANSWERED "nothing here" and a lane that never answered at
    all are not the same event, and collapsing them into `[]` is how a backlog
    silently erases itself: /v1/extract-window stamps extracted_at on a
    zero-fact result, so an unreachable gateway marked turns done while
    learning nothing from them (measured 2026-08-15 — litellm-gw restarted
    mid-window and every candidate model failed to connect). So:

      - model responded, output unusable  -> []      (one window's loss, logged)
      - NO candidate model responded      -> GatewayError

    Callers that can retry (worker.py leaves extracted_at NULL; the backfill
    leaves the turns on its work list) then retry instead of losing the turn.
    """
    models = [m for m in (model or settings.extract_model, settings.extract_fallback_model) if m]
    responded = False
    body: dict[str, Any] = {
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt, mdl in enumerate(models):
            try:
                # The fallback lane needs more than the default ceiling on real
                # windows (ADR-0010 addendum: timed out on 4/6 golden windows
                # at 300s). It only answers when the primary silicon is down
                # and extraction is offline work, so latency is the acceptable
                # cost; a ceiling that kills the lane is not a safety net.
                lane_timeout = (max(timeout, settings.extract_fallback_timeout)
                                if mdl == settings.extract_fallback_model else timeout)
                r = await client.post(f"{settings.litellm_base_url}/chat/completions",
                                      headers=_headers(), json={**body, "model": mdl},
                                      timeout=lane_timeout)
                r.raise_for_status()
                payload = r.json()
                text = (payload["choices"][0]["message"].get("content") or "").strip()
                # EMPTY CONTENT IS NOT AN ANSWER. A thinking model that runs
                # out of budget mid-reasoning returns "" — the lab measured 3
                # of 5 prompts coming back empty at max_tokens=2200 on
                # lab/reason-fast (2026-08-15). Treating "" as "nothing worth
                # keeping" is the same silent-erasure bug as an unreachable
                # gateway, one door over: the caller stamps the turns
                # extracted having learned nothing. "[]" IS an answer — the
                # model looked and found nothing. "" means it never spoke.
                if not text:
                    logger.warning("extract(%s): empty content — treating as failure,"
                                   " not as zero facts (thinking budget?)", mdl)
                    continue
                responded = True          # gave usable content, whatever it said
                objs = salvage_objects(text)
                if not objs and text != "[]":
                    logger.warning("extract(%s): no parsable objects (head=%r)", mdl, text[:200])
                    continue
                return objs
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning("extract(%s) attempt %d failed: %s", mdl, attempt + 1, e)
                await asyncio.sleep(1.5 * (attempt + 1))
    if not responded:
        raise GatewayError(f"no model answered (tried {', '.join(models)})")
    return []


async def embed(texts: Sequence[str], *, timeout: float = 240.0,
                attempts: int = 2) -> list[list[float] | None]:
    """Embed a batch. Returns None per item on failure — never raises.

    A memory with no vector is still a memory: hybrid retrieval degrades to
    keyword + graph (non-negotiable #2 cuts both ways — vector is never the
    only leg, so its absence is survivable). The dream pass can backfill.
    """
    if not texts:
        return []
    # The embedding model shares kaiju with the extraction models, and ollama
    # queues a 334M embedder behind a 70B generation. Under backfill load the
    # lane can stall for minutes — so be patient, then give up cleanly and let
    # the sweeper repair. A memory without a vector is still a memory.
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(f"{settings.litellm_base_url}/embeddings",
                                      headers=_headers(),
                                      json={"model": settings.embed_model,
                                            "input": [t[:6000] for t in texts]})
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                return [d["embedding"] for d in data]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning("embed attempt %d failed for %d texts: %s",
                           attempt + 1, len(texts), e)
            if attempt + 1 < attempts:
                await asyncio.sleep(5)
    return [None] * len(texts)


def to_pgvector(vec: list[float] | None) -> str | None:
    """asyncpg has no native vector codec; pgvector accepts its text form."""
    return None if vec is None else "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
