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

### Infrastructure

```
VPS (Hetzner)
├── Container: scraper-accounting     → Residential Proxy IP #1
├── Container: scraper-admin          → Residential Proxy IP #2
├── Container: scraper-customer-svc   → Residential Proxy IP #3
├── Container: scraper-data-science   → Residential Proxy IP #4
├── Container: scraper-design         → Residential Proxy IP #5
├── Container: scraper-engineering    → Residential Proxy IP #6
├── Container: scraper-it             → Residential Proxy IP #7
├── Container: scraper-legal          → Residential Proxy IP #8
├── Container: scraper-sales          → Residential Proxy IP #9
├── Container: scraper-translation    → Residential Proxy IP #10
├── Container: scraper-webdev         → Residential Proxy IP #11
└── Container: scraper-writing        → Residential Proxy IP #12
```

### Anti-detection Strategy

- One residential proxy IP per container (Bright Data / IPRoyal)
- Randomised start times — containers do not run simultaneously
- 10–30 sec random delay between pages
- 50 pages per category spread over 7 days ≈ 7 pages/day per container
- Each container appears as an independent user from a different country

### Cloudflare Strategy

1. **Residential proxy** — clean IP reputation, Cloudflare rarely triggers
2. **Session persistence** — pass Cloudflare once manually, save `cf_clearance` cookie, reuse for 1–7 days
3. **Capsolver** — fallback automatic Cloudflare solver ($0.001/solve)

### Estimated Cost

| Resource                 | Cost              |
| ------------------------ | ----------------- |
| VPS (Hetzner CX21)       | ~€5/month         |
| 12 residential proxy IPs | ~$30–50/month     |
| **Total**                | **~$35–55/month** |

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
