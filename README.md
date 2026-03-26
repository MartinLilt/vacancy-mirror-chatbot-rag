# vacancy-mirror-chatbot-rag

RAG pipeline for Upwork job vacancies — scrapes, clusters, and serves job market insights via a chatbot.

---

## Architecture Overview

```
Upwork Search Pages (SSR HTML)
    ↓
Scraper (nodriver + real Chrome)
    ↓
data/raw/<category>.json
    ↓
build-job-pattern-csv → normalize → build-job-embeddings
    ↓
data/job_embeddings.jsonl
    ↓
cluster-job-embeddings (bge-large, threshold=0.90)
    ↓
data/job_clusters.json
    ↓
build-top-demanded-profiles → name (gpt-4.1-mini) → semantic-core
    ↓
data/top_demanded_profiles_semantic_core.json
    ↓
RAG Chatbot
```

---

## Pipeline Steps

### 1. Scraping

- Real Chrome via `nodriver` (anti-bot, not headless)
- Data extracted from `window.__NUXT__.state.jobsSearch` (SSR)
- 50 pages × 50 jobs = 2 500 jobs per category
- Delay: 10–30 sec between pages (human-like)
- Checkpoint after every page — safe to interrupt and resume
- 12 Upwork parent categories, one scraper run per category

### 2. Data Preparation

- `build-job-pattern-csv` — extract `uid`, `title`, `description`, `skills` from raw JSON
- `normalize-job-pattern-csv` — lowercase, strip HTML tags and special characters

### 3. Embeddings

- Model: `BAAI/bge-large-en-v1.5` (1024 dimensions, local, no API)
- Output: `data/job_embeddings.jsonl`

### 4. Clustering

- Algorithm: `radius_neighbors_graph` (cosine similarity ≥ 0.90)
- Minimum cluster size: 5 jobs
- Output: `data/job_clusters.json`

### 5. Profile Building

- Top terms from titles and descriptions
- Top skills from `attrs`
- `size` — jobs in cluster core (≥ 0.90)
- `total_matching` — jobs near centroid (soft threshold ≥ 0.80)

### 6. Naming via OpenAI

- Model: `gpt-4.1-mini` (from `OPENAI_MODEL` env var)
- Input: top terms + skills → human-readable role name

### 7. Semantic Core

- Final JSON ready for RAG ingestion

---

## Production Deployment Plan

### Hosting: Hetzner Cloud

**Hetzner Cloud** is the chosen hosting provider. Reasons:

- 3–5× cheaper than AWS/GCP/DigitalOcean for equivalent specs
- Hourly billing — pay only when the server is actually running
- Data centres in Germany, Finland, USA (Ashburn), Singapore
- Native Docker support, persistent Volumes for data storage

**Server type:** `CX42` (8 vCPU, 16 GB RAM) — fits all 12 containers comfortably.

**Billing model:** cron-based, not 24/7.
Scrapers run once per night (~2 hours total). At €0.057/hr that is ≈ **€3–5/month** instead of €20.

```
Hetzner CX42  ~€3–5/month (cron, ~2 h/day)
│
├── Hetzner Volume /data  (shared JSON/JSONL storage)
│
├── Container: scraper-webdev         → Proxy IP #1   (cron: 03:00)
├── Container: scraper-design         → Proxy IP #2   (cron: 03:10)
├── Container: scraper-engineering    → Proxy IP #3   (cron: 03:20)
├── Container: scraper-it             → Proxy IP #4   (cron: 03:30)
├── Container: scraper-data-science   → Proxy IP #5   (cron: 03:40)
├── Container: scraper-sales          → Proxy IP #6   (cron: 03:50)
├── Container: scraper-writing        → Proxy IP #7   (cron: 04:00)
├── Container: scraper-admin          → Proxy IP #8   (cron: 04:10)
├── Container: scraper-accounting     → Proxy IP #9   (cron: 04:20)
├── Container: scraper-customer-svc   → Proxy IP #10  (cron: 04:30)
├── Container: scraper-legal          → Proxy IP #11  (cron: 04:40)
└── Container: scraper-translation    → Proxy IP #12  (cron: 04:50)
```

Containers start staggered (10 min apart) so each looks like an independent user from a different location.

### Anti-detection Strategy

- One residential proxy IP per container (IPRoyal or Bright Data)
- Randomised start times — containers do not run simultaneously
- 10–30 sec random delay between pages
- 50 pages per category spread over 7 days ≈ 7 pages/day per container
- Each container appears as an independent user from a different country

### Cloudflare Strategy

1. **Residential proxy** — clean IP reputation, Cloudflare rarely triggers
2. **Session persistence** — pass Cloudflare once manually, save `cf_clearance` cookie, reuse for 1–7 days
3. **Capsolver** — fallback automatic Cloudflare solver ($0.001/solve)

### Database: PostgreSQL + pgvector

Single database for both structured data and vector search — no separate vector DB needed.

```
PostgreSQL 16 + pgvector extension
│
├── profiles           — role_name, demand_type, demand_ratio, size,
│                        total_matching, category, scraped_at
├── profile_embeddings — vector(1024) per profile (bge-large-en-v1.5)
│                        used for semantic similarity search in RAG
├── scrape_runs        — run timestamp, category, pages collected, status
└── job_samples        — sample jobs per profile (RAG context snippets)
```

**Why not a separate vector DB (Qdrant / Pinecone):**

- pgvector handles `vector(1024)` natively inside Postgres
- JOIN between profiles table and embeddings table works in plain SQL
- Everything backed up with a single `pg_dump`
- At our scale (<10 000 profiles) pgvector is as fast as any dedicated vector DB
- Runs as one more Docker container on the same Hetzner server — zero extra cost

### Estimated Cost

| Resource                      | Cost/month       |
| ----------------------------- | ---------------- |
| Hetzner CX42 (cron, ~2 h/day) | ~€3–5            |
| Hetzner Volume 20 GB          | ~€1              |
| PostgreSQL + pgvector         | €0 (same server) |
| 12 residential proxy IPs      | ~$2–5 (~180 MB)  |
| OpenAI API (naming step)      | ~$2–5            |
| **Total**                     | **~$8–15/month** |

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Add your OPENAI_API_KEY to .env
```

## Run Pipeline

```bash
# Scrape one category
python scripts/run_scraper.py --uid 531770282580668418 --max-pages 50

# Full pipeline
python -m vacancy_mirror_chatbot_rag.cli build-job-pattern-csv
python -m vacancy_mirror_chatbot_rag.cli normalize-job-pattern-csv
python -m vacancy_mirror_chatbot_rag.cli build-job-embeddings
python -m vacancy_mirror_chatbot_rag.cli cluster-job-embeddings
python -m vacancy_mirror_chatbot_rag.cli build-top-demanded-profiles
python -m vacancy_mirror_chatbot_rag.cli name-top-demanded-profiles
python -m vacancy_mirror_chatbot_rag.cli build-semantic-core-profiles
```

## Environment Variables

| Variable         | Description                          |
| ---------------- | ------------------------------------ |
| `OPENAI_API_KEY` | OpenAI API key                       |
| `OPENAI_MODEL`   | Model name (default: `gpt-4.1-mini`) |
