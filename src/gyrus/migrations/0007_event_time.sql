-- ADR-0011 (accepted 2026-08-16): memories carry event time, not just
-- extraction time. The store grading (journal-020) found "time" the
-- second-largest noise class: backfilled news scoring as current (created_at
-- measures the ingest job, not the news) and session-scoped intents frozen as
-- eternal ("Ken wants to avoid email TONIGHT").
--
-- event_at    when the fact was true/observed (source published_at, message
--             Date:, arXiv submission, commit date). NULL = unknown, treat as
--             created_at — today's behaviour, so no backfill is required to ship.
-- valid_until an expiry hint set at extraction ONLY when the fact's own words
--             scope it in time ("tonight", "this week"). The dream pass
--             retires expired rows (soft, as always) instead of waiting for
--             demand decay to starve them.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;

-- The dream pass sweeps expirations; keep that scan off the main index.
CREATE INDEX IF NOT EXISTS idx_memories_valid_until ON memories (valid_until)
    WHERE retired_at IS NULL AND valid_until IS NOT NULL;
