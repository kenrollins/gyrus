-- M4 (ADR-0006): the knowledge tier — insights distilled from curated
-- high-signal sources (conference notes, email, podcasts, arXiv). A fourth
-- signal class in ADR-0002's sense: no outcome, no real corroboration, scored
-- by source authority x recency x retrieval-demand. Down-weighted vs the
-- personal tiers at recall; never enters the M3 procedural metric.

ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_tier_check;
ALTER TABLE memories ADD CONSTRAINT memories_tier_check
    CHECK (tier IN ('procedural', 'factual', 'preference', 'open_loop', 'knowledge'));

-- Source provenance for knowledge memories (null for personal tiers).
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_type TEXT;   -- email|conference|podcast|web|arxiv|conversation
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_ref TEXT;    -- sender | show | url | arXiv id
ALTER TABLE memories ADD COLUMN IF NOT EXISTS topic TEXT[] NOT NULL DEFAULT '{}';

-- ADR-0008: human browsing of the insights surface is the main knowledge-use
-- pattern and MUST count as demand, but it isn't an agent recall — keep it a
-- separate counter so the two signals stay distinguishable. Demand = recall +
-- browse.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS browse_count INT NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_browsed_at TIMESTAMPTZ;

-- Browsing the insights digest by source/topic/recency.
CREATE INDEX IF NOT EXISTS idx_memories_knowledge ON memories (source_type, created_at DESC)
    WHERE retired_at IS NULL AND tier = 'knowledge';
CREATE INDEX IF NOT EXISTS idx_memories_topic ON memories USING gin (topic)
    WHERE retired_at IS NULL;
