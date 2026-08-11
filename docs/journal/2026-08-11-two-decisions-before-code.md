---
id: journal-002-two-decisions-before-code
type: journal
title: "Two decisions before code, and a false dichotomy"
date: 2026-08-11
visibility: public
tags: [m0, decisions, embeddings, topology]
related:
  - adr/0004-own-dmz-service
  - adr/0005-embeddings-via-gateway
one_line: "Run-location and embeddings were gated as 'shape the schema and compose' — one was settled by a firewall direction, the other dissolved once we noticed the gateway's 'metered' path and the 'local' path were the same GPUs."
principle: "Interrogate the options before weighing them — a decision framed as A-vs-B is often A-vs-A with different billing."
---

The task list opened with two decisions deliberately parked above all code:
where gyrus runs, and what embeds its memories. Both were flagged as
schema-shaping — the pgvector dimension is set in migration 0001, and the
compose file needs to know its network before anything deploys.

## Run location: the firewall decided

The options were own DMZ service versus co-located inside the agent's VM. The
deciding facts were all topological. The agent's VM doesn't exist yet (it's
the final migration phase), so "co-located" really meant "lives on the
workstation, then moves." The firewall allows LAN→DMZ and blocks DMZ→LAN, so
a service at a fixed DMZ address is reachable from the workstation today and
from the VM later — the migration becomes a no-op for memory. Metrics
sealed it: Prometheus lives in the DMZ and cannot scrape a LAN co-location,
and the project's falsifiable claim (does procedural recall improve tool
success over sessions?) is *measured through those metrics*. A placement
choice that makes your thesis unmeasurable is not a placement choice.

Consequence accepted with eyes open: the always-injected provider face
becomes a thin HTTP client, and every memory feature lives behind a service
API. One extra LAN hop on recall (~1 ms, against a contract that reads from a
background-populated cache) buys the same seam the future MCP face needs
anyway.

## Embeddings: the dichotomy dissolved

The framed choice was "gateway model (metered, consistent) vs. local Ollama
(zero-token, another dependency)." Verification collapsed it: the gateway's
embedding routes *are* Ollama on the lab's own GPUs — the "metered" path and
the "local" path are the same silicon with different bookkeeping. Zero cloud
cost either way. What the gateway adds is attribution (embedding spend shows
up as this service's own), one consistent model name, and no second inference
daemon to operate. What a private sidecar would add is independence from one
host — bought by violating the platform rule that all inference goes through
the gateway.

Model choice followed the one live precedent in the lineage:
mxbai-embed-large at 1024 dimensions, which the retired predecessor ran in
production behind the same gateway pattern. Its real pgvector trap, we
verified, was never a build failure — it was a docs-vs-migration dimension
mismatch (docs said 1536, migrations said 1024). The schema pins
`vector(1024)`, and the fallback model already pulled on the same host
(bge-m3) is *also* 1024-dim: an upgrade path that needs a re-embed but no
schema migration.

One deliberate deviation: the gateway exposes an `embed` alias that resolves
to the same model, and the scoped key could have been bound to the alias.
It's bound to the concrete model name instead — an alias retarget elsewhere
in the lab must never silently change the dimension under a schema that
can't follow it.

## Related

- [ADR-0004](../adr/0004-own-dmz-service.md) — run location, with consequences
- [ADR-0005](../adr/0005-embeddings-via-gateway.md) — embeddings, with the upgrade path
