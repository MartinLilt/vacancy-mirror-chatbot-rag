# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Repository Layout

Two independent Python packages, each with its own `pyproject.toml` and `src/` layout:

- **`backend/`** — Telegram bot, assistant inference pipeline, FastAPI web API, Stripe/support webhooks
- **`scraper/`** — Upwork headless-Chrome scraper (nodriver), scraper FastAPI API

Shared infrastructure:
- **`infra/`** — nginx config, Docker compose files for production, Grafana dashboards, DB init SQL
- **`notes/`** — Obsidian vault: architecture docs, TODO tracking, knowledge section index
- **`docker-compose.yml`** / **`docker-compose.dev.yml`** — local dev stack
- **`ship.sh`** — one-command build + push + deploy

---

## Running Tests

Both packages use `pytest`. Run from the package root (where `pyproject.toml` lives):

```bash
# backend tests
cd backend && python -m pytest tests/

# single test file
cd backend && python -m pytest tests/test_assistant_infer_client.py

# scraper tests
cd scraper && python -m pytest tests/
```

No linter is configured in pyproject.toml — use `ruff` or `flake8` manually if needed.

---

## Local Dev Stack

```bash
docker compose -f docker-compose.dev.yml up
```

Starts postgres + supporting services locally. The backend and scraper containers are built from source in dev mode.

---

## Deploying to Production

```bash
bash ship.sh backend          # build + push + deploy backend
bash ship.sh scraper          # build + push + deploy scraper
bash ship.sh all              # both
bash ship.sh backend --no-cache
```

`ship.sh` reads `GHCR_USER`, `GHCR_TOKEN`, `BACKEND_SERVER_IP` from `.env` at repo root.

SSH access (port 2222, key `~/.ssh/vacancy_mirror_deploy`):
```bash
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58  # backend
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28  # scraper
```

Open Grafana + monitoring panels locally via SSH tunnel:
```bash
make panels        # start tunnels + open browser windows
make panels-down   # stop tunnels
```

---

## Assistant Pipeline Architecture

The core LLM flow lives in `backend/src/backend/services/assistant/`:

```
Telegram Bot
    │
    ▼
AssistantInferClient   (round-robin + failover across replicas)
    │  POST /v1/answer
    ▼
AssistantInferServer   (ThreadingHTTPServer, BoundedSemaphore max=24)
    │
    ├─ 1. InitOrchestrator.route()     — LLM classifies message → branches[]
    ├─ 2. InitOrchestrator.execute()   — branches run in parallel (ThreadPoolExecutor)
    └─ 3. ResultOrchestrator.synthesize() — 1 branch: direct return; 2+: LLM merges
```

**Branches** (`orchestrator.py` → `Branch` enum):
- `knowledge` — RAG over 40 knowledge sections (`knowledge.py`). Layer 1: LLM decides whether retrieval is needed. If yes, `AssistantSectionRetriever` uses weighted lexical scoring (not vector search) to pick top-k sections.
- `statistics` — weekly market reports per Upwork category. Layer 1: LLM decides category. Report fetch is currently a **stub** in `statistics_branch.py` (`_fetch_weekly_report`).
- `simple` — fallback for greetings/small talk. Never runs alongside business branches.

**LLM implementation:** `openai.py` wraps the OpenAI API via raw `urllib` (no SDK). `generate_structured_json()` uses `response_format: json_object`. `answer_with_history()` is for plain chat. Model defaults to `gpt-4.1-mini`.

**Scaling:** production runs 3 replicas (`assistant-infer-1/2/3`) on port `8090`. `AssistantInferClient` load-balances via `ASSISTANT_INFER_URLS` env var.

---

## Scraper Architecture

`scraper/src/scraper/` — headless Chrome via `nodriver`, with:
- `webshare.py` — rotating residential proxy (Webshare)
- `flaresolverr_client.py` — Cloudflare bypass via FlareSolverr sidecar
- `upwork_scraper.py` — main scraping logic, writes to `raw_jobs` table

`scraper/src/scraper_api/main.py` — FastAPI control plane:
- `POST /scrape` — trigger scrape run (requires `X-API-Key`)
- `GET /jobs` — paginated raw jobs
- `POST /jobs/clear` — truncate raw_jobs (weekly reset)
- Public: `/health`, `/status`, `/categories`, `/chaos-state`

---

## Key Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | backend | OpenAI API calls |
| `OPENAI_MODEL` | backend | Model name (default: `gpt-4.1-mini`) |
| `TELEGRAM_BOT_TOKEN` | backend | Bot token |
| `ASSISTANT_INFER_URLS` | backend | Comma-separated infer replica URLs |
| `ASSISTANT_INFER_PORT` | infer server | HTTP port (default: `8090`) |
| `ASSISTANT_INFER_MAX_CONCURRENCY` | infer server | Semaphore limit (default: `24`) |
| `DB_URL` | backend | PostgreSQL connection |
| `DATABASE_URL` | scraper | PostgreSQL connection |
| `PROXY_URL` | scraper | Webshare rotating proxy |
| `SCRAPER_API_KEY` | scraper API | API auth key |
| `ALLOWED_USER_IDS` | telegram bot | Comma-separated Telegram IDs (empty = open) |

---

## Production Servers

| Server | IP | Key services |
|--------|----|-------------|
| Backend | `178.104.113.58` | Telegram bot, 3× assistant-infer, FastAPI api, support-webhook (Stripe), Chatwoot, Grafana, Postgres |
| Scraper | `178.104.110.28` | Scraper + cron, FlareSolverr, scraper-api, Prometheus, Grafana, Postgres |

Production compose files: `infra/deploy/docker-compose.backend.yml` and `infra/deploy/docker-compose.scraper.yml`. Live on servers at `/etc/vacancy-mirror/`.

---

## Notes Vault

`notes/` is an Obsidian vault with living design docs:
- `Architecture — Assistant Pipeline.md` — pipeline diagram and LLM call budget per scenario
- `Knowledge Sections — Index.md` — all 40 RAG sections with IDs and retrieval logic
- `TODO — Assistant.md` — current work items and done list