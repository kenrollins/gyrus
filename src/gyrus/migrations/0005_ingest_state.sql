-- gyrus's cursor for pulling source-items from thalamus (ADR-0007: gyrus is the
-- consumer; it tracks where it's read to). One row per upstream source.
CREATE TABLE IF NOT EXISTS ingest_state (
    source  TEXT PRIMARY KEY,
    cursor  BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
