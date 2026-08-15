# ADR-0009: Email enters thalamus by edge-collector push, not a thalamus fetcher

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Ken (lane approved; architecture delegated), Fable

## Context

The M5 email lane must feed Ken's high-value newsletter signal into the
knowledge tier, including a ~300-message historical backlog. ADR-0007 says
thalamus owns acquisition, which implies a thalamus Gmail adapter. But
inspection of the Pip VM (2026-08-15) found a **live, complete acquisition
pipeline already running there** under Hermes cron: Gmail API fetch (OAuth
token + refresh watchdog), normalization to a filesystem lake (812 messages,
clean extracted text), deterministic sender routing, and — decisively — a
**curated source-profile allowlist** (`pip_signal_profiles.py` +
`source-profiles.yaml`: canonical name, sender addresses, reliability tier,
priority). Only the pipeline's final hop (promotion into OpenBrain) is
orphaned; everything upstream runs daily.

Duplicating this in thalamus would mean a second Google OAuth app, a second
token to babysit, and a re-implementation of measured normalization and
routing — violating non-negotiable #6 (don't reinvent the proven parts) — while
the original kept running anyway, because it also feeds Pip's Obsidian briefs.

## Decision

**The Pip VM keeps acquisition; a thin pusher forwards allowlisted-sender
messages to thalamus.**

- thalamus gains `POST /v1/ingest`: accepts batches of contract `SourceItem`s
  from edge collectors, guarded by a shared secret (`THALAMUS_PUSH_TOKEN`),
  fail-closed when unconfigured. Dedup by content hash as with fetched lanes.
- The Pip VM gains `pip_thalamus_push.py`: joins the lake's message index to
  the sender allowlist, maps clean text → `SourceItem` (`source_type="email"`,
  `source_ref`=message-id, `author`=canonical source, `topic`=[source, tier]),
  pushes incrementally on a cursor; `--backlog` for history.
- gyrus treats `email` as a **trusted** source (extract all, no relevance
  gate) — legitimate *only because the allowlist gate already ran at the
  edge*. Raw unfiltered mail must never be pushed under this source_type.

## Consequences

- **The ADR-0007 boundary holds where it matters:** gyrus still consumes only
  the source-item contract from thalamus and knows nothing of the Pip VM.
  What changes is that thalamus now has two intake modes — pull (its own
  adapters: arXiv, GitHub) and authenticated push (edge collectors whose
  credentials legitimately live elsewhere). This is the standard
  pushgateway-style topology for unscrapeable sources.
- **No new credentials anywhere:** Gmail OAuth never leaves the Pip VM; Ken
  provided nothing.
- The sender allowlist (`~/.hermes/source-profiles.yaml` on the Pip VM) is now
  the email lane's front gate. Adding a newsletter to the lane = adding it
  there, no code change in thalamus or gyrus.
- Coupling cost: the lane's liveness depends on the Pip VM's Hermes cron and
  the pusher's cron entry — one more hop than a native adapter. Accepted; the
  hop is idempotent (content-hash dedup) and quiet-on-empty.
