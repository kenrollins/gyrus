-- ADR-0014 / review 2026-10-20.
-- (1) withheld: recall that was computed and logged but NOT shown to the agent
--     (the control arm). Never bumps recall_count, never scored as followed.
ALTER TABLE memory_retrievals ADD COLUMN IF NOT EXISTS withheld BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS memory_retrievals_pending_idx
    ON memory_retrievals (turn_id) WHERE followed_computed_at IS NULL;

-- (2) One-off repair of the demand signal (review D1/D9). recall_count had
--     been bumped by every /v1/prefetch call: cron sessions reading their own
--     bookkeeping (1,295 of 3,370 rows in the 21 days before 2026-10-20) and
--     the provider's post-turn warm-up (a second copy of every turn's recall).
--     Recount as distinct recall EVENTS (one per second per memory) from
--     non-cron sessions. From here on only served, non-cron recalls count.
UPDATE memories m SET recall_count = sub.n
FROM (
    SELECT memory_id, count(DISTINCT date_trunc('second', retrieved_at)) AS n
    FROM memory_retrievals
    WHERE session_id NOT LIKE 'cron\_%' AND session_id <> 'review-probe'
    GROUP BY memory_id
) sub WHERE sub.memory_id = m.id;
UPDATE memories SET recall_count = 0
WHERE recall_count > 0 AND NOT EXISTS (
    SELECT 1 FROM memory_retrievals r
    WHERE r.memory_id = memories.id
      AND r.session_id NOT LIKE 'cron\_%' AND r.session_id <> 'review-probe');
