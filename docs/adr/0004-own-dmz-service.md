# ADR-0004: gyrus runs as its own DMZ service on `.11`, not co-located with Hermes

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** Ken

## Context

ARCHITECTURE §9.2 left run-location open: gyrus as its own DMZ service
(`10.0.13.11`, the reserved allocation) that the Pip VM calls, vs. co-located
inside the Hermes VM. The platform facts, verified against
`/data/code/dmz/ONBOARDING.md` and `docs/HERMES-INTEGRATION.md`:

- The Hermes VM does not exist until integration Phase 4; today Pip runs on
  shadesmar (LAN). "Co-located" would mean gyrus lives on Ken's workstation
  first, then migrates with Pip — two homes, one move.
- LAN→DMZ is allowed, DMZ→LAN is blocked. A service on `.11` is reachable from
  shadesmar now and from the Hermes VM later — the same address before and
  after migration ("relocation, not rewiring").
- The dream pass is a timer job; it wants an always-on lab host, not a
  workstation.
- Prometheus (`.203`, DMZ) cannot scrape a LAN co-location — the M6 metrics,
  including the procedural success curve that measures the falsifiable claim,
  require gyrus in the DMZ.
- All backends (Supabase `.220`, Neo4j `.224`, gateway `.201`) are DMZ.
- The MCP face (M5) needs a stable service address behind the existing
  Caddy/Authentik pattern; own-service gets it free.

## Decision

**gyrus is its own DMZ tenant on `10.0.13.11`** (compose shape in `LAB.md`:
`dmz13` leg + private `gyrus_net` bridge). Consequently the Hermes
`MemoryProvider` face is a **thin HTTP client**: the provider ABC runs inside
the Hermes process on shadesmar (later the Hermes VM) and calls the gyrus
service over HTTP. All memory logic lives in the service.

## Consequences

- gyrus exposes a small HTTP API from M0 (sync/prefetch at minimum). This is
  the same seam the MCP face needs later — built once.
- One extra LAN hop on `prefetch` (~1 ms); acceptable because `prefetch`
  returns from a background-populated cache by contract (ADR-0003).
- Pip's Phase-4 migration is a no-op for memory.
- The provider client must degrade gracefully when gyrus is unreachable
  (empty recall, buffered sync) — Pip must never block on memory.
