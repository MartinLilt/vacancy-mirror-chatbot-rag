-- Migration: add ciphertext column to raw_jobs
-- Run once on the existing database.
-- ciphertext is Upwork's other job identifier (~0123abc format).
-- job_uid already stores whichever was non-null (uid preferred).
-- This column stores the ciphertext explicitly for cross-referencing.

ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS ciphertext TEXT;

-- Index for fast lookup by ciphertext (e.g. to match with Upwork URLs)
CREATE INDEX IF NOT EXISTS raw_jobs_ciphertext_idx ON raw_jobs (ciphertext)
WHERE
    ciphertext IS NOT NULL;

COMMENT ON COLUMN raw_jobs.ciphertext IS 'Upwork ciphertext job identifier (~0abc... format). ' 'Stored alongside job_uid (numeric uid) for cross-referencing.';