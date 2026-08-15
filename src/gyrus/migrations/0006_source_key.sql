-- Corroboration requires independence (ADR-0002). The email lane showed the
-- write-path near-dup fold counting a newsletter's own templated boilerplate
-- (legal footers, author bios — one per issue) as "corroboration": 29 bumps
-- from one source repeating itself. source_key names the canonical origin
-- (newsletter name, github repo, arXiv id family) so persist() can decline
-- the bump when the duplicate comes from the same source. NULL = unknown /
-- conversation, which keeps the pre-existing behaviour.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_key TEXT;
