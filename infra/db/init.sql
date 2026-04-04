-- ---------------------------------------------------------------------------
-- vacancy-mirror-chatbot-rag — PostgreSQL schema
-- Runs automatically on first postgres container start via
-- /docker-entrypoint-initdb.d/init.sql
-- ---------------------------------------------------------------------------

-- Enable pgvector extension for semantic similarity search.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- scrape_runs — audit log of every scraper execution
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    category_uid TEXT NOT NULL,
    category_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    pages_collected INT NOT NULL DEFAULT 0,
    jobs_collected INT NOT NULL DEFAULT 0,
    jobs_inserted INT NOT NULL DEFAULT 0, -- new rows actually written
    jobs_skipped INT NOT NULL DEFAULT 0, -- duplicates skipped
    duration_seconds INT, -- computed on finish
    status TEXT NOT NULL DEFAULT 'running', -- running | done | failed
    error_message TEXT
);

-- ---------------------------------------------------------------------------
-- profiles — one row per named role profile
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
    id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT REFERENCES scrape_runs (id) ON DELETE SET NULL,
    category_uid TEXT NOT NULL,
    category_name TEXT NOT NULL,
    cluster_id INT NOT NULL,
    role_name TEXT NOT NULL,
    auto_role_name TEXT,
    demand_type TEXT NOT NULL, -- broad | niche | exotic
    demand_ratio NUMERIC(8, 2) NOT NULL DEFAULT 0,
    size INT NOT NULL DEFAULT 0,
    total_matching INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (
        category_uid,
        cluster_id,
        created_at
    )
);

-- ---------------------------------------------------------------------------
-- profile_embeddings — vector(1024) per profile for RAG semantic search
-- Uses BAAI/bge-large-en-v1.5 (1024 dimensions).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_embeddings (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    embedding vector (1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast cosine similarity search over profile embeddings.
CREATE INDEX IF NOT EXISTS profile_embeddings_vector_idx ON profile_embeddings USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 10);

-- ---------------------------------------------------------------------------
-- subscriptions — Telegram user subscription state managed via Stripe
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    plan TEXT NOT NULL, -- 'free' | 'plus' | 'pro_plus'
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- 'active' | 'cancelled' | 'past_due'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- job_samples — individual job postings linked to a profile (RAG context)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_samples (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    jobid TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    skills TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (profile_id, jobid)
);

-- ---------------------------------------------------------------------------
-- raw_jobs — raw scraped vacancy records, one row per Upwork job posting.
-- Populated by the scraper container before any clustering / embedding.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_jobs (
    id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT REFERENCES scrape_runs (id) ON DELETE SET NULL,
    category_uid TEXT NOT NULL,
    category_name TEXT NOT NULL,
    job_uid TEXT NOT NULL,       -- numeric uid (preferred) or ciphertext
    ciphertext TEXT,             -- Upwork ~0abc... identifier (raw, unmodified)
    title TEXT NOT NULL,
    description TEXT,
    published_at TIMESTAMPTZ,
    job_type SMALLINT,                   -- 1 = fixed, 2 = hourly
    duration_label TEXT,                 -- e.g. 'Less than 1 month'
    client_country TEXT,
    client_payment_verified BOOLEAN,
    client_total_spent NUMERIC(14, 2),
    client_total_reviews INT,
    client_total_feedback NUMERIC(5, 2),
    enterprise_job BOOLEAN NOT NULL DEFAULT FALSE,
    skills TEXT[],                       -- attrs[].prefLabel
    hourly_budget_min NUMERIC(10, 2),
    hourly_budget_max NUMERIC(10, 2),
    weekly_budget NUMERIC(12, 2),
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (category_uid, job_uid)
);

-- Index for fast lookups by category and scrape run.
CREATE INDEX IF NOT EXISTS raw_jobs_category_uid_idx ON raw_jobs (category_uid);

CREATE INDEX IF NOT EXISTS raw_jobs_scrape_run_id_idx ON raw_jobs (scrape_run_id);

-- ---------------------------------------------------------------------------
-- proxy_usage_snapshots — real proxy usage telemetry (Webshare API)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- support_feedback_events — Contact Support events from Telegram bot
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS support_feedback_events (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_username TEXT NOT NULL DEFAULT '',
    telegram_full_name TEXT NOT NULL DEFAULT '',
    reply_channel TEXT NOT NULL, -- telegram | email | none
    reply_email TEXT NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS support_feedback_events_created_at_idx
    ON support_feedback_events (created_at DESC);

CREATE INDEX IF NOT EXISTS support_feedback_events_user_id_idx
    ON support_feedback_events (telegram_user_id);

