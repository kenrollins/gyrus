-- M0: episodic scratch. Raw turns land here (episodic IS the scratch tier —
-- non-negotiable #1 forbids raw transcripts as *memory*, extraction is M1).
-- `messages` keeps the full OpenAI-style turn slice, tool calls included and
-- untruncated: the M3 tip_followed judge needs the verbatim action record
-- (gemma-forge had to reconstruct it from run JSONL; we keep it from day one).

CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    platform    TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS episodic_turns (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    turn_index      INT,
    platform        TEXT,
    user_text       TEXT NOT NULL DEFAULT '',
    assistant_text  TEXT NOT NULL DEFAULT '',
    messages        JSONB,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    consolidated_at TIMESTAMPTZ,
    fts tsvector GENERATED ALWAYS AS (
        to_tsvector('english', left(coalesce(user_text, '') || ' ' || coalesce(assistant_text, ''), 100000))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON episodic_turns (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_turns_created ON episodic_turns (created_at DESC);
-- The dream pass eats unconsolidated rows (signal-forge idempotency pattern).
CREATE INDEX IF NOT EXISTS idx_turns_unconsolidated ON episodic_turns (created_at) WHERE consolidated_at IS NULL;
-- Keyword leg of M1 hybrid retrieval.
CREATE INDEX IF NOT EXISTS idx_turns_fts ON episodic_turns USING gin (fts);
