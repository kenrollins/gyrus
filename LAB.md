# gyrus — lab allocation

This file records THIS service's lab allocation. The platform contract
(networking, secrets, inference, DNS, telemetry rules) lives in
**`/data/code/dmz/ONBOARDING.md`** — read it there, don't copy it here.

## Status: RESERVED, not yet provisioned

Design is complete; the service isn't built. The allocation below is reserved.
Secret-minting and the Authentik/Caddy/DNS steps happen at **build kickoff**
(and only if/when a public MCP face is wanted — v1 is reachable LAN→DMZ only,
so it may never need a passkey hostname).

| | |
|---|---|
| VLAN-13 address | `10.0.13.11` — inherited from the retired openbrain (poetic: the successor takes the memory-service address) |
| Private backends | `gyrus_net` bridge (no VLAN address) for anything that must not face the DMZ |
| Shared Postgres | `10.0.13.220:5432` — **be a client** (own DB `gyrus`), don't stand up a rival |
| Neo4j + Graphiti | `10.0.13.224` (bolt `:7687`) — reflective/bi-temporal tier |
| Inference | gateway `http://10.0.13.201:4000/v1` — extraction + embeddings. Mint a scoped key `gyrus` at kickoff (into `/data/docker/gyrus/.env`, 600) |
| Embeddings | **decided (ADR-0005):** gateway `kaiju/mxbai-embed-large`, `vector(1024)`; `bge-m3` (same dim) is the upgrade path |
| Prometheus | scrape target added at kickoff (consolidation runs, memory counts, recall latency) |

## Who reaches it

- **Pip / Hermes** (LAN, and later a VM on xr7620) — the always-injected
  `MemoryProvider` client. LAN→DMZ is allowed, so it reaches `.11` directly.
- **Claude / OpenAI / Gemini** (future) — the MCP face; needs a deliberate,
  authenticated internet exposure before it leaves the LAN. Not v1.

## Compose shape (at build)

```yaml
networks:
  gyrus_net: {driver: bridge}     # private backends — no VLAN address
  dmz13: {external: true}

services:
  app:
    env_file: /data/docker/gyrus/.env
    networks:
      gyrus_net: {}
      dmz13: {ipv4_address: 10.0.13.11}   # DMZ isolation needs a dmz13 leg, not just reachability
```

## Remaining manual step (at kickoff, relayed through Ken)

Operator adds — **only if a public face is wanted** — the internal Unbound
override `gyrus.lab.kenrollins.dev` → `10.0.13.3` (specific host, never a
wildcard) plus the Authentik app + Caddy route. v1 needs none of this.
