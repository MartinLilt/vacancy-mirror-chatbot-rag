-- Migration: add proxy_usage_snapshots for real Webshare usage telemetry
-- Run this once on existing databases:
--   psql "$DATABASE_URL" < infra/db/migrate_proxy_usage_snapshots.sql

CREATE TABLE IF NOT EXISTS proxy_usage_snapshots (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'webshare',
    source_endpoint TEXT,
    requests_used BIGINT,
    bytes_used BIGINT,
    bytes_remaining BIGINT,
    bytes_limit BIGINT,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS proxy_usage_snapshots_captured_at_idx
    ON proxy_usage_snapshots (captured_at);

