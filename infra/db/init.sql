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