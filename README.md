# Vacancy Mirror

Production monorepo with two independent runtime domains:

- `backend/` -> Telegram bot, Stripe webhook, RAG pipeline
- `scraper/` -> Upwork ingestion (chaos mode), FlareSolverr, scraper API

This README is operator-first and reflects the **current stable scraper approach**.

## System Boundaries (Important)

- **Backend server**: `178.104.113.58`
- **Scraper server**: `178.104.110.28`
- Scraper incidents must be handled in `scraper/` + `infra/deploy/docker-compose.server2.yml`.
- Do not modify backend runtime to fix scraper network/proxy failures.

## Current Working Scraper Pipeline

1. `chaos_runner.sh` starts from cron or manual `start`.
2. Scraper requests page HTML via FlareSolverr (`/v1`).
3. HTML is validated (Cloudflare/ban/Chrome error checks).
4. Scraper browser (nodriver + Chromium) extracts `__NUXT__` and jobs.
5. Dedup + writes into Postgres on scraper server.
6. State is persisted in `/app/data/chaos_state.json`.

## Proxy Strategy (Critical)

Proxy settings are intentionally split:

- `PROXY_URL` -> used by **scraper Chrome** (nodriver)
- `FLARESOLVERR_PROXY_URL` -> used by **FlareSolverr**

Default stable setup:

- `PROXY_URL` = residential proxy (optional, for scraper browser)
- `FLARESOLVERR_PROXY_URL` = empty (FlareSolverr direct egress)

Reason: some authenticated proxy formats break Chromium inside FlareSolverr and cause:

- `ERR_NO_SUPPORTED_PROXIES`
- local Chrome error HTML (~246 KB)

## Configuration

Root `.env` (minimal scraper-related keys):

```dotenv
BACKEND_SERVER_IP=178.104.113.58
SCRAPER_SERVER_IP=178.104.110.28

PROXY_URL=
FLARESOLVERR_PROXY_URL=
```

Server 2 compose (`infra/deploy/docker-compose.server2.yml`) already maps:

- `flaresolverr.environment.PROXY_URL: ${FLARESOLVERR_PROXY_URL:-}`
- `scraper.environment.PROXY_URL: ${PROXY_URL:-}`

## Deploy Commands

Use from repo root.

```bash
bash ship.sh scraper
```

Or step-by-step:

```bash
bash infra/deploy/push-images.sh scraper
bash infra/deploy/deploy.sh scraper
```

`infra/deploy/deploy.sh` for scraper now recreates both containers:

- `flaresolverr`
- `scraper`

so env/config changes apply immediately.

## Run / Observe Scraper

Manual run on scraper server:

```bash
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
cd /etc/vacancy-mirror
docker exec scraper /app/scripts/chaos_runner.sh
```

Live logs:

```bash
docker exec scraper tail -f /var/log/scraper.log
docker logs -f flaresolverr
```

## Incident Runbook: `ERR_NO_SUPPORTED_PROXIES`

Symptoms:

- scraper log: `FlareSolverr proxy BROKEN`
- FlareSolverr returns Chrome error page
- HTML often around ~246 KB with `<title>www.upwork.com</title>`

Steps:

1. Check FlareSolverr env:

```bash
docker exec flaresolverr env | grep PROXY_URL
```

2. Temporarily disable FlareSolverr proxy (safe mode):

```bash
sed -i 's|^FLARESOLVERR_PROXY_URL=.*|FLARESOLVERR_PROXY_URL=|' /etc/vacancy-mirror/.env
cd /etc/vacancy-mirror
docker compose up -d --no-deps --force-recreate flaresolverr scraper
```

3. Verify FlareSolverr response is no longer proxy-error page:

```bash
curl -s -X POST http://localhost:8191/v1 \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"request.get","url":"https://www.upwork.com/nx/search/jobs/?q=python&sort=recency","maxTimeout":60000}'
```

4. Start scraper session again and watch logs.

## Repo Map (Operational)

- `scraper/scripts/chaos_runner.sh` -> main cron entrypoint
- `scraper/src/scraper/services/upwork_scraper.py` -> page load and extraction logic
- `infra/deploy/docker-compose.server2.yml` -> scraper production stack
- `infra/deploy/deploy.sh` -> deployment orchestration
- `ship.sh` -> build + push + deploy wrapper

## Guardrails for Operators

- Treat scraper and backend as separate systems.
- For scraper outages: touch only scraper-related compose/env/scripts first.
- Validate runtime behavior with server-side checks before claiming fix.
- Do not assume `docker compose restart` reloads `.env`; use recreate when env changed.

## Quick Health Checklist

```bash
# On scraper server
cd /etc/vacancy-mirror
docker compose ps

docker exec flaresolverr env | grep PROXY_URL
curl -s http://localhost:8191/health

docker exec scraper python3 -c 'import scraper; print("ok")'
```

If all checks pass, scraper can be started safely from the console/UI.
