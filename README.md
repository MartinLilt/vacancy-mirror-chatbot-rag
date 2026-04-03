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

Current stable setup:

- `PROXY_URL` = residential proxy for nodriver Chrome
- `FLARESOLVERR_PROXY_URL` = **sticky residential proxy** for FlareSolverr

Important: scraper resilience now depends on dedicated FlareSolverr proxy + runtime timeout handling.

## Configuration

Root `.env` (minimal scraper-related keys):

```dotenv
BACKEND_SERVER_IP=178.104.113.58
SCRAPER_SERVER_IP=178.104.110.28

PROXY_URL=
FLARESOLVERR_PROXY_URL=
WEBSHARE_API_KEY=

# FlareSolverr anti-timeout knobs
FLARESOLVERR_MAX_TIMEOUT_MS=120000
FLARESOLVERR_TIMEOUT_COOLDOWN_SEC=35
FLARESOLVERR_TIMEOUT_BACKOFF_MULT=1.8
FLARESOLVERR_ROTATE_AFTER_TIMEOUTS=2
```

Server 2 compose (`infra/deploy/docker-compose.server2.yml`) already maps:

- `flaresolverr.environment.PROXY_URL: ${FLARESOLVERR_PROXY_URL:-}`
- `scraper.environment.PROXY_URL: ${PROXY_URL:-}`
- `scraper.environment.FLARESOLVERR_PROXY_URL: ${FLARESOLVERR_PROXY_URL:-}`
- `scraper.environment.FLARESOLVERR_*` timeout/backoff/rotation knobs
- `scraper.environment.WEBSHARE_API_KEY: ${WEBSHARE_API_KEY:-}`

## Cloudflare Timeout Handling (Current)

In `scraper/src/scraper/services/upwork_scraper.py`:

- FlareSolverr solve timeout is configurable (`FLARESOLVERR_MAX_TIMEOUT_MS`, default `120000`).
- Timeout retries use separate cooldown/backoff (defaults `35s`, multiplier `1.8`).
- After repeated timeout errors, scraper rotates FlareSolverr proxy session username (when proxy username supports session pattern).

Typical timeout symptom in logs:

- `FlareSolverr HTTP error 500 ... Timeout after 120.0 seconds.`
- `Timeout cooldown before retry ...`
- `Rotated FlareSolverr proxy session username` (when rotation succeeded)

If you see `Proxy session rotation skipped: username has no session pattern`, check that scraper container actually received `FLARESOLVERR_PROXY_URL` with sticky/session-capable username.

## Real Proxy Usage Telemetry

Proxy usage is collected from Webshare API and stored in Postgres table `proxy_usage_snapshots`.

- CLI command: `python -m scraper.cli collect-proxy-usage`
- Cron inside scraper container: every 15 minutes
- Grafana panel `Residential Proxy Usage (MB/h, real)` reads real usage from DB snapshots

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

## Incident Runbook: FlareSolverr Timeout / Proxy Issues

Symptoms:

- scraper log: `FlareSolverr HTTP error 500 ... Timeout after ...`
- repeated `Error solving the challenge`
- or `FlareSolverr proxy BROKEN` / Chrome error HTML

Steps:

1. Check env in both containers:

```bash
docker exec flaresolverr env | grep PROXY_URL
docker exec scraper env | grep -E 'PROXY_URL|FLARESOLVERR_PROXY_URL|FLARESOLVERR_MAX_TIMEOUT_MS'
```

2. Verify sticky proxy is present in `/etc/vacancy-mirror/.env`:

```bash
grep -E '^FLARESOLVERR_PROXY_URL=' /etc/vacancy-mirror/.env
```

3. Recreate both services after env/compose changes:

```bash
cd /etc/vacancy-mirror
docker compose up -d --no-deps --force-recreate flaresolverr scraper
```

4. Verify FlareSolverr health:

```bash
curl -s http://localhost:8191/health
```

5. Start scraper session again and watch logs.

## Repo Map (Operational)

- `scraper/scripts/chaos_runner.sh` -> main cron entrypoint
- `scraper/src/scraper/services/upwork_scraper.py` -> page load and extraction logic
- `scraper/src/scraper/services/webshare.py` -> Webshare proxy usage collector
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
