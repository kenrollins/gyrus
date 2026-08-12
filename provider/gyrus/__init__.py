"""gyrus — Hermes MemoryProvider face (thin HTTP client, ADR-0004).

Install: copy this directory to $HERMES_HOME/plugins/gyrus/ on the Hermes
host (shadesmar; later the Hermes VM) and set in Hermes config.yaml:

    memory:
      provider: gyrus

Config (env, or `hermes memory setup`):
    GYRUS_BASE_URL — the gyrus service, default http://10.0.13.11:8000

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
import os
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:  # bundled-vs-user install path (plugins.memory vs _hermes_user_memory)
    from agent.memory_provider import MemoryProvider
except ImportError:  # pragma: no cover
    from hermes.agent.memory_provider import MemoryProvider  # type: ignore

logger = logging.getLogger(__name__)

_TIMEOUT_S = 3.0        # writes (queued, off the turn path)
_RECALL_TIMEOUT_S = 2.5  # the hard deadline Pip's turn will ever wait on recall
_QUEUE_MAX = 256  # drop oldest beyond this — memory must never OOM the agent


class GyrusMemoryProvider(MemoryProvider):
    """Always-injected face of the gyrus store."""

    def __init__(self) -> None:
        self._base_url = os.environ.get("GYRUS_BASE_URL", "http://10.0.13.11:8000").rstrip("/")
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
        return bool(self._base_url)

    # -- lifecycle ------------------------------------------------------------

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._platform = kwargs.get("platform", "")
        # cron/subagent/flush contexts must not pollute Ken's episodic record.
        self._write_only = kwargs.get("agent_context", "primary") != "primary"
        self._writer = threading.Thread(target=self._writer_loop, name="gyrus-writer", daemon=True)
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
        threading.Thread(
            target=self._refresh_cache, args=(query, session_id or self._session_id),
            name="gyrus-prefetch", daemon=True,
        ).start()

    def _fetch_recall(self, query: str, session_id: str, *, timeout: float):
        params = urllib.parse.urlencode({"session_id": session_id, "q": query})
        data = self._request("GET", f"/v1/prefetch?{params}", timeout=timeout)
        return None if data is None else data.get("text", "")

    def _refresh_cache(self, query: str, session_id: str) -> None:
        key = query.strip()[:500]
        text = self._fetch_recall(key, session_id, timeout=_TIMEOUT_S)
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
            self._queue.put_nowait({"path": "/v1/turns", "body": payload})
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
            self._queue.put_nowait({"path": f"/v1/sessions/{sid}/end", "body": {}})
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
            self._request("POST", item["path"], item["body"])

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
                 timeout: float = _TIMEOUT_S) -> Optional[Dict[str, Any]]:
        req = urllib.request.Request(
            self._base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.debug("gyrus %s %s failed: %s", method, path, e)
            return None
