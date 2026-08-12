-- M1: the semantic tier — extracted facts, not transcripts (non-negotiable #1).
--
-- Tier is the thesis (ADR-0002): each row carries its signal source, and the
-- dream pass runs the right evaluator per tier. `memory_retrievals` is the
-- gemma-forge `tip_retrievals` analogue and exists NOW, before M3 needs it,
-- so signal PRODUCTION (the per-tier evaluator, later) stays cleanly separated
-- from signal CONSUMPTION (ranking, eviction, credit) — the one property of
-- the ported design worth protecting from day one.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memories (
    id              BIGSERIAL PRIMARY KEY,
    tier            TEXT NOT NULL CHECK (tier IN ('procedural', 'factual', 'preference', 'open_loop')),
    fact            TEXT NOT NULL,
    entities        TEXT[] NOT NULL DEFAULT '{}',
    -- 'relayed' added 2026-08-12 from the golden-set grading: Ken transcribing
    -- a conference speaker is NOT Ken asserting a fact. Conflating them would
    -- let a speaker's claim inherit Ken's authority.
    provenance      TEXT NOT NULL DEFAULT 'observed'
                    CHECK (provenance IN ('ken_said', 'observed', 'relayed', 'assistant_suggested')),
    embedding       vector(1024),              -- ADR-0005: kaiju/mxbai-embed-large
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 0.5,   -- learned by the dream pass
    weight          DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    success_count   INT NOT NULL DEFAULT 0,
    failure_count   INT NOT NULL DEFAULT 0,
    fact_hash       TEXT NOT NULL,             -- exact-dup guard; near-dup is cosine at write
    source_turn_id  BIGINT REFERENCES episodic_turns(id) ON DELETE SET NULL,
    source_session_id TEXT,
    extractor       TEXT,                      -- model+prompt version that produced it
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_recalled_at TIMESTAMPTZ,
    recall_count    INT NOT NULL DEFAULT 0,
    corroboration_count INT NOT NULL DEFAULT 1,   -- factual tier's signal
    -- Bi-temporal: NEVER hard-delete a memory (gemma-forge eviction.py ports
    -- as-is only if retirement is soft).
    retired_at      TIMESTAMPTZ,
    retired_reason  TEXT,
    superseded_by_id BIGINT REFERENCES memories(id) ON DELETE SET NULL,
    consolidated_at TIMESTAMPTZ,               -- signal-forge idempotency pattern
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english', fact)) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_hash_live
    ON memories (fact_hash) WHERE retired_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_memories_live ON memories (tier, created_at DESC) WHERE retired_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_memories_fts ON memories USING gin (fts);
CREATE INDEX IF NOT EXISTS idx_memories_entities ON memories USING gin (entities);
CREATE INDEX IF NOT EXISTS idx_memories_unconsolidated ON memories (created_at) WHERE consolidated_at IS NULL;
-- ivfflat needs training rows to be useful; harmless while the table is small.
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 64);

-- Flat entity resolution (openbrain harvest) — the graph leg of hybrid
-- retrieval without requiring Neo4j on the hot path.
CREATE TABLE IF NOT EXISTS memory_entities (
    id          BIGSERIAL PRIMARY KEY,
    memory_id   BIGINT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity      TEXT NOT NULL,
    normalized  TEXT NOT NULL,          -- lower(trim(entity)); canonical form
    UNIQUE (memory_id, normalized)
);
CREATE INDEX IF NOT EXISTS idx_entities_norm ON memory_entities (normalized);

-- Every recall, logged. The dream pass (M2) and credit assignment (M3) read
-- outcome_value / followed_* from here; nothing else writes them.
CREATE TABLE IF NOT EXISTS memory_retrievals (
    id              BIGSERIAL PRIMARY KEY,
    memory_id       BIGINT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    session_id      TEXT,
    turn_id         BIGINT REFERENCES episodic_turns(id) ON DELETE SET NULL,
    rank            INT,
    score           DOUBLE PRECISION,
    query           TEXT,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- written later by the per-tier evaluator (M3) — the "swap the evaluator" seam
    outcome_value       DOUBLE PRECISION,
    outcome_confidence  DOUBLE PRECISION,
    followed_llm        BOOLEAN,
    followed_emb        DOUBLE PRECISION,
    followed_computed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_retrievals_memory ON memory_retrievals (memory_id);
CREATE INDEX IF NOT EXISTS idx_retrievals_pending ON memory_retrievals (session_id)
    WHERE followed_computed_at IS NULL AND outcome_value IS NOT NULL;

-- Extraction bookkeeping: which turns have been through the pass, and what
-- happened. Makes the backfill idempotent and resumable.
ALTER TABLE episodic_turns ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;
ALTER TABLE episodic_turns ADD COLUMN IF NOT EXISTS extract_error TEXT;
CREATE INDEX IF NOT EXISTS idx_turns_unextracted ON episodic_turns (created_at)
    WHERE extracted_at IS NULL;
