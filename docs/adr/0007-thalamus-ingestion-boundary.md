# ADR-0007: Ingestion is a separate service (thalamus); gyrus consumes a source-item contract

- **Status:** Accepted
- **Date:** 2026-08-13
- **Deciders:** Ken

## Context

ADR-0006 brought curated high-signal sources (conference, email, podcast, web,
arXiv) into gyrus as a knowledge tier. The open question was *where the
ingestion machinery lives*: co-located with Pip on shadesmar, or as a
DMZ-native service. Two forces decided it. First, reuse: Ken wants a core
ingestion capability that Pip can call and that other things (RAGFlow, a
dashboard, future agents) can leverage — not a gyrus-private feeder. Second,
separation of concerns: fetch / transcribe / schedule / retry is operationally
different from store / consolidate / recall, and folding acquisition into a
memory project would bloat it.

## Decision

**Ingestion is its own tenant and repo — `thalamus` — separate from gyrus.**
The name is deliberate: the thalamus is the brain's sensory relay, the hub that
filters and routes incoming signal to the cortex, which is where memory lives.
gyrus (cortex/memory) is fed by thalamus (the senses).

The boundary is a **normalized source-item contract**, and it falls where the
work changes kind:

- **thalamus = acquisition + normalization** (source-shaped). Fetch email /
  podcast / RSS / arXiv, transcribe audio, strip boilerplate, deduplicate,
  attribute (source_type, source_ref, author, date, url). Output: a clean,
  attributed **source item**. thalamus does **no memory extraction** and, as a
  rule, **no "understanding" LLM work** — its ML is limited to acquisition
  (e.g. Whisper transcription). It has its own store and its own REST/MCP API.
- **gyrus = extraction + memory** (memory-shaped). Pulls source items, runs the
  extraction pass into the knowledge tier, scores and consolidates. This is
  what gyrus already does well; it gains one client for one endpoint, not a
  fetch subsystem.

**Dependency direction: gyrus → the source-item contract, only.** thalamus has
zero awareness that gyrus exists. gyrus PULLS new items on its offline
consolidation cadence (which also satisfies "consolidate offline, never
mid-turn"); thalamus just accumulates and serves. Pip (and others) call
thalamus's command API to trigger a fetch or query items. Both services sit on
the DMZ, so DMZ↔DMZ pull works without the shadesmar firewall constraint.

Email keeps its fetch on shadesmar for now (Gmail OAuth + the existing
`brief_items` pipeline live there); only its OUTPUT repoints into the flow.
When email should become Pip-independent, its fetch migrates into thalamus with
a dedicated credential.

## Consequences

- gyrus stays memory-focused; thalamus is independently deployable, scalable,
  and reusable — delete thalamus and gyrus merely stops getting new knowledge;
  delete gyrus and thalamus keeps serving everyone else.
- Two projects, two repos, two ADR trails. thalamus's own design (adapters,
  store, API) is recorded in ITS repo; gyrus records only its side — the
  consumption contract (this ADR).
- The contract is small and versioned: a source item is
  `{source_type, source_ref, title, body, author, published_at, url, topic[],
  content_hash}`. Changing it is a coordinated change across two repos; keep it
  minimal.
- thalamus provisioning (own `.1x` address, gateway key, compose) happens at its
  build kickoff, not now — same discipline as gyrus's own allocation.
- The heavy-fetch capability thalamus needs for ADR-0008 (pull full source on
  demand) lives here too — thalamus acquires at both depths.
