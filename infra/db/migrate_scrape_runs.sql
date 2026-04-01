-- Migration: add jobs_inserted, jobs_skipped, duration_seconds to scrape_runs
-- Run this once on existing databases:
--   psql $DATABASE_URL < infra/db/migrate_scrape_runs.sql

ALTER TABLE scrape_runs
ADD COLUMN IF NOT EXISTS jobs_inserted INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS jobs_skipped INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS duration_seconds INT;