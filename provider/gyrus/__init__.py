"""gyrus — Hermes MemoryProvider face (thin HTTP client, ADR-0004).

Install: copy this directory (``__init__.py`` + ``plugin.yaml``) to
$HERMES_HOME/plugins/gyrus/ on the Hermes host (the pip VM) and set in Hermes
config.yaml:

    memory:
      provider: gyrus

Config ($HERMES_HOME/.env, or `hermes memory setup`):
    GYRUS_BASE_URL  — the gyrus service, default http://10.0.13.11:8000
    GYRUS_API_TOKEN — bearer for the service (M7); unset = open posture

Hermes contract (v0.21.5+, plugins/AGENTS.md):
  - both values are read with agent.secret_scope.get_secret, never os.environ:
    under a multiplexed gateway a profile's .env is NOT in os.environ, and an
    unscoped read fails closed.
  - every background thread starts via spawn_context_thread, and each queued
    write carries the context of the turn that queued it (ctx_bound), so the
    writer reads the token under that turn's secret scope / HERMES_HOME.
  - no on-disk state, so nothing is keyed by hermes_home.

Design constraints honored here:
  - prefetch() must return fast: it only reads a cache that queue_prefetch()
    populates from a background thread (ADR-0003).
  - Pip must never block on memory: every network call is threaded, short-
    timeout, and failure degrades to empty recall / dropped sync — never an
    exception into the agent loop.
  - sync_turn ships the FULL message list (tool calls untruncated): the M3
    causal-attribution judge needs the verbatim action record.

stdlib-only on purpose — no new deps in the Hermes venv.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider, ctx_bound, spawn_context_thread
from agent.secret_scope import UnscopedSecretError, get_secret

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://10.0.13.11:8000"
_TIMEOUT_S = 3.0        # writes (queued, off the turn path)
_RECALL_TIMEOUT_S = 2.5  # the hard deadline Pip's turn will ever wait on recall
_QUEUE_MAX = 256  # drop oldest beyond this — memory must never OOM the agent


def _resolve_base_url() -> str:
    """GYRUS_BASE_URL from the active profile's secret scope (falls through to
    os.environ in a single-profile process, exactly as before)."""
    return (get_secret("GYRUS_BASE_URL", _DEFAULT_BASE_URL) or "").rstrip("/")


class GyrusMemoryProvider(MemoryProvider):
    """Always-injected face of the gyrus store."""

    def __init__(self) -> None:
        # Construction may run outside any profile scope (discovery, doctor), so
        # no secret read here; initialize() resolves the real value.
        self._base_url = _DEFAULT_BASE_URL
        self._session_id = ""
        self._platform = ""
        self._write_only = False  # non-primary contexts skip writes entirely
        self._turn_index = 0
        self._cache_lock = threading.Lock()
        self._prefetch_cache = ""
        self._cache_key = None
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=_QUEUE_MAX)
        self._writer: Optional[threading.Thread] = None

    # -- identity / activation ------------------------------------------------

    @property
    def name(self) -> str:
        return "gyrus"

    def is_available(self) -> bool:
        # Config-only check by contract (no network). The URL always has a
        # default, so gyrus is "available" whenever explicitly selected.
        try:
            return bool(_resolve_base_url())
        except UnscopedSecretError:  # probed outside a profile scope (multiplex)
            return bool(_DEFAULT_BASE_URL)

    def get_config_schema(self) -> List[Dict[str, Any]]:
        # Env-only provider: every field carries env_var, so `hermes memory
        # setup` writes them to $HERMES_HOME/.env and save_config stays a no-op.
        return [
            {"key": "base_url", "description": "gyrus service URL",
             "default": _DEFAULT_BASE_URL, "env_var": "GYRUS_BASE_URL"},
            {"key": "api_token", "description": "gyrus API bearer token (blank = open posture)",
             "secret": True, "required": False, "env_var": "GYRUS_API_TOKEN"},
        ]

    # -- lifecycle ------------------------------------------------------------

    def initialize(self, session_id: str, **kwargs) -> None:
        self._base_url = _resolve_base_url()
        self._session_id = session_id
        self._platform = kwargs.get("platform", "")
        # cron/subagent/flush contexts must not pollute Ken's episodic record.
        self._write_only = kwargs.get("agent_context", "primary") != "primary"
        self._writer = spawn_context_thread(self._writer_loop, name="gyrus-writer")
        self._writer.start()

    def shutdown(self) -> None:
        try:
            self._queue.put_nowait(None)  # sentinel: drain and stop
        except queue.Full:
            pass
        if self._writer is not None:
            self._writer.join(timeout=5.0)

    # -- recall (read face) ---------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall for THIS turn: cache hit, else a bounded synchronous fetch.

        The pure-cache reading of this hook (populate in queue_prefetch, serve
        the cache here) looks right and is wrong for a LAN service: the first
        turn of every session gets nothing, and later turns get recall for the
        PREVIOUS question. Verified live 2026-08-12 — Pip answered correctly
        from its built-in memory while gyrus logged no retrieval at all.

        Measured round trip from the agent host is ~120 ms warm, so recall is
        fetched inline against a hard 2.5 s deadline (the tail case is a cold
        embedding lane). Miss the deadline and the turn proceeds with no
        memory rather than a stale one — showing the previous question's
        memories is worse than showing none.
        """
        key = query.strip()[:500]
        with self._cache_lock:
            if self._cache_key == key:
                return self._prefetch_cache
        text = self._fetch_recall(key, session_id or self._session_id,
                                  timeout=_RECALL_TIMEOUT_S)
        if text is None:
            return ""
        with self._cache_lock:
            self._cache_key, self._prefetch_cache = key, text
        return text

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Warm the cache (and the embedding lane) between turns."""
        spawn_context_thread(
            self._refresh_cache, args=(query, session_id or self._session_id),
            name="gyrus-prefetch",
        ).start()

    def _fetch_recall(self, query: str, session_id: str, *, timeout: float,
                      log: bool = True):
        params = urllib.parse.urlencode(
            {"session_id": session_id, "q": query, "log": 1 if log else 0})
        data = self._request("GET", f"/v1/prefetch?{params}", timeout=timeout)
        return None if data is None else data.get("text", "")

    def _refresh_cache(self, query: str, session_id: str) -> None:
        # Warm-up only (log=0): this fires after the turn with the question
        # just answered, and gyrus was recording it as a second recall and
        # attributing it to the NEXT turn (review D9, 2026-10-20). It still
        # warms the embedding lane and the cache; it no longer counts.
        key = query.strip()[:500]
        text = self._fetch_recall(key, session_id, timeout=_TIMEOUT_S, log=False)
        if text is not None:
            with self._cache_lock:
                self._cache_key, self._prefetch_cache = key, text

    # -- capture (write face) -------------------------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if self._write_only:
            return
        self._turn_index += 1
        payload = {
            "session_id": session_id or self._session_id,
            "turn_index": self._turn_index,
            "platform": self._platform,
            "user_text": user_content or "",
            "assistant_text": assistant_content or "",
            "messages": messages,
            "meta": {},
        }
        try:
            self._queue.put_nowait({"path": "/v1/turns", "body": payload,
                                   "send": ctx_bound(self._request)})
        except queue.Full:
            logger.warning("gyrus write queue full — dropping turn (memory must not block Pip)")

    def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "",
                          reset: bool = False, rewound: bool = False, **kwargs) -> None:
        self._session_id = new_session_id
        if reset:
            self._turn_index = 0
            with self._cache_lock:
                self._prefetch_cache, self._cache_key = "", None

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if self._write_only or not self._session_id:
            return
        sid = urllib.parse.quote(self._session_id, safe="")
        try:
            self._queue.put_nowait({"path": f"/v1/sessions/{sid}/end", "body": {},
                                   "send": ctx_bound(self._request)})
        except queue.Full:
            pass

    # -- tools (none in M0) ---------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []

    # -- plumbing ---------------------------------------------------------------

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            # Run under the context of the turn that queued it (its secret scope
            # and HERMES_HOME), not the context the writer was spawned in.
            item["send"]("POST", item["path"], item["body"])

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
                 timeout: float = _TIMEOUT_S) -> Optional[Dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        # M7 auth (Fable F3): the service requires a bearer once
        # GYRUS_API_TOKEN is set on both sides. Absent env = the historic
        # open posture, so the provider stays deployable against either.
        try:
            token = get_secret("GYRUS_API_TOKEN", "") or ""
        except UnscopedSecretError as e:
            # Multiplexed and no profile scope: fail closed (never fall back to
            # another profile's token, never send unauthenticated) and degrade.
            logger.warning("gyrus %s %s skipped: %s", method, path, e)
            return None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            self._base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.debug("gyrus %s %s failed: %s", method, path, e)
            return None


def register(ctx) -> None:
    """Memory-provider entry point (plugins/memory discovery and plugin doctor)."""
    ctx.register_memory_provider(GyrusMemoryProvider())
