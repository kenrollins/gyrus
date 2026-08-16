-- ADR-0013: the fast-read projection for the reflective tier. Entity
-- co-occurrence is computed IN the Neo4j graph nightly (graph.enrich) and
-- written back here so the retrieval graph-leg expands query entities one
-- hop without ever paying a bolt round-trip. Empty until the first
-- enrichment run; the retrieval query tolerates empty, not absent.
CREATE TABLE IF NOT EXISTS entity_relations (
    entity      TEXT NOT NULL,
    related     TEXT NOT NULL,
    weight      INT  NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity, related)
);
CREATE INDEX IF NOT EXISTS idx_entity_relations_entity ON entity_relations (entity);
