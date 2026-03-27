# vacancy-mirror-chatbot-rag

RAG pipeline for Upwork job vacancies — scrapes, clusters, and serves job market insights via a Telegram chatbot.

---

## Architecture Overview

```
Upwork Search Pages (SSR HTML)
         ↓
Scraper Server (CPX11 × N)          ← unique IP per server, anti-bot
nodriver + real Chrome
         ↓
INSERT INTO raw_jobs                 ← writes directly to remote PostgreSQL
         ↓  (Hetzner Private Network)
Backend Server (CPX32)
         ↓
7-step pipeline (run-full-pipeline)
  1. build-pattern-jobs
  2. normalize-pattern-jobs
  3. build-job-embeddings            ← BAAI/bge-large-en-v1.5 (1024-dim)
  4. cluster-job-embeddings          ← NearestNeighbors, cosine similarity
  5. build-top-demanded-profiles
  6. name-top-demanded-profiles      ← OpenAI gpt-4-mini
  7. build-semantic-core-profiles
         ↓
PostgreSQL + pgvector
         ↓
Telegram Bot (RAG chatbot)           ← answers user queries 24/7
```

---

## 🗺️ Roadmap

### ✅ Phase 0 — Core Pipeline (DONE)

- [x] Scraper with nodriver (real Chrome, anti-bot)
- [x] 7-step pipeline: pattern → normalize → embed → cluster → profiles → name → semantic core
- [x] PostgreSQL + pgvector storage (all file I/O removed)
- [x] `run-full-pipeline` orchestrator command
- [x] Tested locally with 2500 Web Dev jobs

### 🔧 Phase 1 — Split into two Docker images (NOW)

- [ ] `Dockerfile.backend` — pipeline + telegram-bot (runs on CPX32)
- [ ] `Dockerfile.scraper` — only nodriver scraper (runs on CPX11)
- [ ] `docker-compose.backend.yml` — postgres + pipeline + bot
- [ ] `docker-compose.scraper.yml` — single scraper, configurable via env
- [ ] Deploy CPX32 backend + CPX11 scraper on Hetzner (Helsinki)
- [ ] Category: **Web, Mobile & Software Dev** (first live run)

### 👀 Phase 2 — Observe & Harden (2–3 weeks)

- [ ] Monitor daily pipeline runs (cron logs, error alerts)
- [ ] Tune clustering threshold and profile quality
- [ ] Build **AI orchestrator** (multi-turn chat, tool calls)
- [ ] Add **RAG tools**: profile search, job examples, trend queries
- [ ] Telegram bot UI polish

### 🚀 Phase 3 — Second Category + Go Public

- [ ] Add **Design & Creative** scraper (second CPX11)
- [ ] Validate pipeline handles 2 categories correctly
- [ ] Launch publicly, attract first users
- [ ] Gather feedback, iterate

### 📈 Phase 4 — Scale (when ready)

- [ ] Add remaining 10 categories (one CPX11 each)
- [ ] Full 12-category coverage, ~€58/month
- [ ] Analytics dashboard

---

## Pipeline Steps

### 1. Scraping (`upwork-scraper` service)

- Real Chrome via `nodriver` — bypasses bot detection without proxies
- Data extracted from `window.__NUXT__.state.jobsSearch` (Upwork SSR JSON)
- 50 pages × 50 jobs = 2500 jobs per category per run
- Random delay 10–30 sec between pages (human-like behaviour)
- Checkpoint after every page — safe to interrupt and resume
- Writes directly into `raw_jobs` table in PostgreSQL (no local files)
- Each scraper server has its own public IP — no proxy needed

### 2. Pattern Extraction (`build-job-pattern-csv`)

- Reads from `raw_jobs` table
- Extracts: `uid`, `title`, `description`, `skills`, `category_uid`
- Writes to `pattern_jobs` table
- Idempotent — `ON CONFLICT DO NOTHING` skips already processed jobs

### 3. Normalisation (`normalize-job-pattern-csv`)

- Reads from `pattern_jobs` table
- Lowercases text, strips HTML tags, removes special characters
- Writes to `pattern_normalized_jobs` table

### 4. Embeddings (`build-job-embeddings`)

- Model: `BAAI/bge-large-en-v1.5` (1024 dimensions, runs locally, no API)
- Batch size: 32 jobs per inference pass (~2.5 min for 2500 jobs on CPU)
- Writes `vector(1024)` per job into `job_embeddings` table (pgvector)
- Skips jobs already embedded — safe to rerun

### 5. Clustering (`cluster-job-embeddings`)

- Algorithm: `NearestNeighbors` with cosine similarity, radius threshold 0.94
- Builds connected components graph → extracts top clusters by size
- Writes cluster assignments to `job_clusters` table

### 6. Profile Building (`build-top-demanded-profiles`)

- Reads clusters + jobs from DB
- Computes `demand_ratio`, `total_matching`, `demand_type` (broad/niche/exotic)
- Writes one row per cluster into `profiles` table

### 7. Naming via OpenAI (`name-top-demanded-profiles`)

- Reads profiles from `profiles` table
- Sends top terms + skills to OpenAI `gpt-4-mini`
- Updates `role_name` field with human-readable name (e.g. "Full-Stack React Developer")
- Cost: ~$0.01–0.05 per pipeline run (6–12 profiles)

### 8. Semantic Core (`build-semantic-core-profiles`)

- Reads profiles + sample jobs from DB
- Builds structured JSON with n-gram patterns, top skills, sample titles
- Updates `semantic_core` field in `profiles` table
- This JSON is the RAG context used by the Telegram bot

---

## Production Deployment Plan

### Hosting: Hetzner Cloud — Distributed Architecture

Two tiers of servers connected via **Hetzner Private Network** (free, 10 Gbit/s internal).

#### Tier 1 — Backend Server (CPX32, Helsinki)

One permanent server that runs all heavy processing:

```
CPX32 — 4 vCPU, 8 GB RAM, 80 GB SSD — €12.69/month
└── Docker Compose
    ├── postgres       (24/7)  — pgvector:pg16, all data lives here
    ├── pipeline       (4h/day) — embeddings + clustering + profiles
    │                             starts at 06:00 UTC, exits when done
    └── telegram-bot   (24/7)  — RAG chatbot, answers user queries
                                  calls OpenAI API for chat responses
```

RAM budget:

```
postgres:      ~1.0 GB  (always)
telegram-bot:  ~0.3 GB  (always)
pipeline:      ~4.0 GB  (only during 4h run, then releases)
────────────────────────
Peak:          ~5.3 GB  (safe on 8 GB)
Idle:          ~1.3 GB
```

#### Tier 2 — Scraper Servers (CPX11 × N, Helsinki)

One cheap server per Upwork category. Each has its own **unique public IP** — Upwork sees them as independent users.

```
CPX11 — 2 vCPU, 2 GB RAM, 40 GB SSD — €3.79/month each

scraper-webdev      (IP #1)  → category: Web, Mobile & Software Dev
scraper-design      (IP #2)  → category: Design & Creative
scraper-datasci     (IP #3)  → category: Data Science & Analytics
... (one per category, added gradually)
```

Each scraper:

- Runs nodriver (real Chrome) once per day at night
- Writes raw jobs **directly into postgres** on the Backend via Private Network
- Uses `DB_URL=postgresql://app:pass@10.0.0.X:5432/vacancy_mirror`
- Has no local database, no embeddings model — just scraping

#### Hetzner Private Network

```
Private Network: 10.0.0.0/24 (free)

Backend:    10.0.0.1   ← postgres listens here
Scraper #1: 10.0.0.2   → writes to 10.0.0.1:5432
Scraper #2: 10.0.0.3   → writes to 10.0.0.1:5432
Scraper #3: 10.0.0.4   → writes to 10.0.0.1:5432
```

PostgreSQL port 5432 is **never exposed to the public internet** — only reachable from inside the private network.

### Anti-detection Strategy

- Each scraper server has its own **unique public IP** — no proxy needed
- Real Chrome via `nodriver` (not headless Selenium/Playwright)
- 10–30 sec random delay between pages
- Human-like session: cookies, localStorage, realistic User-Agent
- Staggered cron start times (10 min apart per scraper)

### Database: PostgreSQL + pgvector

Single database for both structured data and vector search.

```
PostgreSQL 16 + pgvector
├── raw_jobs                — raw scraped JSON per job
├── pattern_jobs            — extracted uid, title, description, skills
├── pattern_normalized_jobs — cleaned, lowercased text
├── job_embeddings          — vector(1024) per job (bge-large-en-v1.5)
├── job_clusters            — cluster assignments
├── profiles                — role_name, demand_type, demand_ratio
├── profile_embeddings      — vector(1024) per profile (RAG search)
└── scrape_runs             — audit log per scraper run
```

### Scaling Plan

| Phase         | Servers           | Categories | Monthly Cost |
| ------------- | ----------------- | ---------- | ------------ |
| **MVP (now)** | CPX32 + 1× CPX11  | 1          | **€16.48**   |
| **Growth**    | CPX32 + 3× CPX11  | 3          | **€24.06**   |
| **Full**      | CPX32 + 12× CPX11 | 12         | **€58.17**   |

Add a new scraper = spin up one more CPX11, set `CATEGORY_UID` + `DB_URL` in `.env`, done.

### Estimated Monthly Cost (MVP)

| Resource                 | Cost           |
| ------------------------ | -------------- |
| CPX32 Backend            | €12.69         |
| CPX11 Scraper ×1         | €3.79          |
| Private Network          | €0             |
| OpenAI API (naming step) | ~$0.50         |
| **Total**                | **~€17/month** |

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Fill in DB_URL, OPENAI_API_KEY in .env
```

## Run Pipeline

```bash
# Import raw JSON into DB (one-time or after scraping)
python -m vacancy_mirror_chatbot_rag.cli import-raw-to-db

# Run all 7 pipeline steps at once
python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline

# Or run individual steps
python -m vacancy_mirror_chatbot_rag.cli build-job-pattern-csv
python -m vacancy_mirror_chatbot_rag.cli normalize-job-pattern-csv
python -m vacancy_mirror_chatbot_rag.cli build-job-embeddings
python -m vacancy_mirror_chatbot_rag.cli cluster-job-embeddings
python -m vacancy_mirror_chatbot_rag.cli build-top-demanded-profiles
python -m vacancy_mirror_chatbot_rag.cli name-top-demanded-profiles
python -m vacancy_mirror_chatbot_rag.cli build-semantic-core-profiles
```

## Environment Variables

| Variable         | Description                        |
| ---------------- | ---------------------------------- |
| `DB_URL`         | PostgreSQL connection string       |
| `OPENAI_API_KEY` | OpenAI API key                     |
| `OPENAI_MODEL`   | Model name (default: `gpt-4-mini`) |
| `CATEGORY_UID`   | Upwork category UID to scrape      |
| `PROXY_URL`      | Optional proxy for scraper         |
