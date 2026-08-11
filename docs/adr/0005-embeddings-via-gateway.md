# ADR-0005: Embeddings via the gateway (`kaiju/mxbai-embed-large`), schema `vector(1024)`

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** Ken

## Context

ARCHITECTURE §9.3 framed the choice as gateway model (metered, consistent) vs.
local Ollama (zero-token, another dep). Source verification (2026-08-11)
reframed it:

- **No inherited dimension.** gemma-forge never shipped an embedding pipeline:
  its `vector(768)` column is written by nothing and read by nothing; the only
  embedding use is an in-process MiniLM scalar cosine for the follow-judge.
  signal-forge deliberately shipped without embeddings. Greenfield choice.
- **The gateway path is already local.** The gateway routes
  `kaiju/mxbai-embed-large` (1024-dim, 512 ctx) and `kaiju/nomic-embed-text`
  (768-dim, 2048 ctx) to kaiju's Ollama — zero cloud cost, metered,
  attributable. A private Ollama sidecar would only buy independence from
  kaiju, at the cost of an extra dep, unmetered spend, and skirting
  non-negotiable "inference only via the gateway."
- **The lineage precedent is exactly this shape**: openbrain ran
  mxbai-embed-large @1024 behind a LiteLLM alias. Its real pgvector trap was
  a docs-vs-migration dimension mismatch (1536 vs 1024), not a build failure.
- kaiju also has `bge-m3` pulled (1024-dim, 8192 ctx) but unrouted.

## Decision

**All embeddings go through the gateway using `kaiju/mxbai-embed-large`;
pgvector columns are `vector(1024)`.** The gyrus scoped key must include the
embedding model in its scope. The model name is config, not code.

## Consequences

- 512-token context is sufficient because gyrus embeds extracted facts, never
  transcripts (non-negotiable #1).
- `bge-m3` is a drop-in upgrade path (same 1024 dimension): one gateway config
  stanza + a re-embed, no schema migration.
- If kaiju is down, embedding fails; by design hybrid retrieval degrades to
  keyword + graph, and ingest queues embeddings for retry. No inline hard
  dependency on the embedder.
- Embedding spend appears in the gateway's metering as gyrus's own.
