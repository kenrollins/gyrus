---
id: gotcha-005-hermes-memory-provider-scope-contract
type: gotcha
title: "A memory provider's writer thread can't see the secret it needs unless the turn hands it over"
date: 2026-10-07
visibility: public
tags: [hermes, provider, secrets, threading]
related:
  - adr/0003-provider-plus-mcp-face
one_line: "Hermes v0.21.5 scopes secrets per profile and runs memory work under the turn's context, so a provider that reads its token from os.environ inside a bare threading.Thread sends unauthenticated requests the moment the gateway serves more than one profile — read with agent.secret_scope.get_secret and queue writes as ctx_bound callables on threads from spawn_context_thread."
principle: "Long-lived worker threads must carry the context of the request that queued the work, not the context they were started in."
---

**Symptom.** None, in Pip's configuration today: one profile per gateway process,
where Hermes' secret reader falls through to `os.environ`, so the old provider
kept working after the 2026-10-07 upgrade (v0.21.3 → v0.21.5; recall and
`POST /v1/turns` 201 verified on the server log). The failure is latent. In a
scratch home with the gateway's multiplexed, profile-scoped mode simulated
(measured 2026-10-07, loopback stub server), the v1.0 provider sent its writes to
the `os.environ` URL with **no `Authorization` header**, and the stub received nothing.

**Mechanism.** Two rules in the v0.21.5 memory-provider contract
(`plugins/AGENTS.md`, `memory-provider-plugin.md`):

- Credentials come from `agent.secret_scope.get_secret`, never `os.environ`. Under a
  multiplexed gateway a profile's `.env` is never loaded into the process
  environment, and an unscoped read fails closed.
- Background work starts via `agent.memory_provider.spawn_context_thread`, never a
  bare `threading.Thread`. A bare thread starts with an empty context, so the scope
  the turn established is gone.

The provider's `gyrus-writer` is long-lived: it is spawned once in `initialize()` and
drains a queue for every later turn. Spawning it correctly is not enough on its own,
because it would carry the *initialize* context forever. Each queued item has to
carry the context of the turn that queued it.

**Fix** (`provider/gyrus` v1.1.0):

```python
from agent.memory_provider import MemoryProvider, ctx_bound, spawn_context_thread
from agent.secret_scope import UnscopedSecretError, get_secret

self._writer = spawn_context_thread(self._writer_loop, name="gyrus-writer")
self._queue.put_nowait({"path": "/v1/turns", "body": payload,
                        "send": ctx_bound(self._request)})   # turn's context rides along
# in _request: token = get_secret("GYRUS_API_TOKEN", "")  (UnscopedSecretError -> skip, warn)
```

Proved in the same scratch run: under a scope the writer's POST carried the scoped
token; a later turn queued under a *different* scope was sent with that turn's token;
an item queued with no scope was skipped with a warning and the writer stayed alive.
Single-profile traffic to the stub was byte-identical to v1.0 (sorted request log
diff). The provider also gained a `plugin.yaml` and `register(ctx)`; without the
manifest `hermes plugins doctor gyrus` reported "not found".

**Boundary.** Tested against Hermes v0.21.5 (cbffbeecf4) only. The provider now
imports `ctx_bound`, `spawn_context_thread` and `agent.secret_scope`, so it no
longer loads on a Hermes that predates them.
