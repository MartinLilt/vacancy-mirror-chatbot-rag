# Infrastructure Overview

Last updated: 2026-04-07

## Servers

| Server | IP | Primary Role |
|--------|----|--------------|
| Backend | `178.104.113.58` | Telegram bot, Stripe/support webhooks, Chatwoot, Grafana, PostgreSQL |
| Scraper | `178.104.110.28` | Scraper, FlareSolverr, Prometheus, Grafana, PostgreSQL |

SSH access (key-only, passwords disabled):
```bash
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58   # backend
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28   # scraper
```

---

## Production Environment

### Backend Server (Production) `178.104.113.58`

#### Services

| Service | Type | Port | Access | Purpose |
|---------|------|------|--------|---------|
| **nginx** | Host (systemd) | `0.0.0.0:80` | Public | Reverse proxy for `/webhook` and `/pay/*` |
| **backend** (Telegram bot) | Docker | — | Internal only | Telegram long-polling worker |
| **support-webhook** | Docker | `127.0.0.1:8080` | Localhost only | Stripe webhook + support endpoints |
| **postgres** (pgvector) | Docker | `127.0.0.1:5432` | Localhost only | Product DB |
| **grafana-backend** | Docker | `127.0.0.1:3001` | Localhost only | Backend monitoring |
| **chatwoot-rails** | Docker | `127.0.0.1:3002` | Localhost only | Support UI |
| **chatwoot-sidekiq** | Docker | — | Internal only | Chatwoot worker queue |
| **chatwoot-redis** | Docker | — | Internal only | Chatwoot cache/queue store |
| **chatwoot-postgres** | Docker | — | Internal only | Chatwoot DB |

#### Nginx (host-level)

Located at `/etc/nginx/sites-enabled/vacancy-mirror`:

- `vacancy-mirror.com /webhook` -> `http://127.0.0.1:8080/webhook`
- `vacancy-mirror.com /pay/` -> `http://127.0.0.1:8080`
- `vacancy-mirror.com /` -> redirect to `https://vacancy-mirror.com` (Vercel)

#### Compose and env (production)

- Compose file on server: `/etc/vacancy-mirror/docker-compose.yml`
- Source in repo: `infra/deploy/docker-compose.backend.yml`
- Env file: `/etc/vacancy-mirror/backend.env`

#### Firewall (UFW)

```text
Status: active
Default: deny incoming, allow outgoing

22/tcp    ALLOW    Anywhere    # SSH
80/tcp    ALLOW    Anywhere    # HTTP
443/tcp   ALLOW    Anywhere    # HTTPS (reserved for future SSL)
```

### Scraper Server (Production) `178.104.110.28`

#### Services

| Service | Type | Port | Access |
|---------|------|------|--------|
| **scraper** | Docker | `127.0.0.1:8000` | Localhost only |
| **flaresolverr** | Docker | `127.0.0.1:8191` | Localhost only |
| **postgres** | Docker | `127.0.0.1:5432` | Localhost only |
| **prometheus** | Docker | `127.0.0.1:9090` | Localhost only |
| **grafana** | Docker | `127.0.0.1:3000` | Localhost only |
| **node-exporter** | Docker | — | Internal only |

#### Compose and env (scraper)

- Compose file on server: `/etc/vacancy-mirror/docker-compose.yml`
- Source in repo: `infra/deploy/docker-compose.server2.yml`
- Env file: `/etc/vacancy-mirror/.env`

#### Cron

```text
0 2 * * *  /etc/vacancy-mirror/rotate_webshare_proxy.sh
```

#### Firewall (UFW)

```text
Status: active
Default: deny incoming, allow outgoing

22/tcp    ALLOW    Anywhere    # SSH
```

---

## Backend Development Environment (planned replica on backend server)

This section defines a dedicated backend dev stack isolated from production.

### Scope

- Host stays the same: `178.104.113.58`
- Dev stack runs from separate path and env
- Dev must use separate credentials/tokens from production

### Paths (dev)

- Compose path: `/etc/vacancy-mirror-dev/docker-compose.yml`
- Env file: `/etc/vacancy-mirror-dev/backend.dev.env`
- Optional Grafana provisioning path: `/etc/vacancy-mirror-dev/grafana-backend/provisioning`

### Services (dev replica)

| Service | Suggested container name | Suggested bind | Access |
|---------|---------------------------|----------------|--------|
| Backend bot | `backend-dev` | — | Internal only |
| Support webhook | `support-webhook-dev` | `127.0.0.1:18080` | Localhost only |
| Postgres | `postgres-dev` | `127.0.0.1:15432` | Localhost only |
| Grafana (optional) | `grafana-backend-dev` | `127.0.0.1:13001` | Localhost only |
| Chatwoot (optional full replica) | `chatwoot-*-dev` | `127.0.0.1:13002` (rails) | Localhost only |

### Mandatory credential split (prod != dev)

- `TELEGRAM_BOT_TOKEN` (separate dev bot)
- `DB_URL` (dev DB)
- `STRIPE_WEBHOOK_SECRET` and Stripe links (test mode)
- `CHATWOOT_*` tokens/IDs (dev workspace/inbox)
- `SUPPORT_API_TOKEN`
- `CHATWOOT_WEBHOOK_TOKEN`
- Prefer separate `GOOGLE_SHEETS_ID` for dev sync

### Access model for dev

- Keep dev services localhost-bound
- Use SSH tunnel for local browser access (Grafana/Chatwoot dev)
- If external webhook testing is needed, add a dedicated dev nginx route/subdomain to `127.0.0.1:18080`

### Suggested dev deployment flow

```bash
# 1) Build and push dev-tagged backend image
docker build -t ghcr.io/<GHCR_USER>/vacancy-mirror-backend:dev ./backend
docker push ghcr.io/<GHCR_USER>/vacancy-mirror-backend:dev

# 2) On backend server, deploy only dev stack
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58
cd /etc/vacancy-mirror-dev
docker compose pull
docker compose up -d
docker compose ps
docker compose logs backend-dev --tail 50
```

### Rollback (dev)

```bash
# Set previous known-good image tag in dev compose/env and recreate containers
cd /etc/vacancy-mirror-dev
docker compose up -d
```

---

## Security Hardening (applied 2026-04-07)

1. Squid open proxy removed (`*:3128`).
2. SSH password auth disabled; key-only access.
3. UFW enabled with deny-incoming default.
4. Docker services bound to `127.0.0.1` where applicable.
5. Host nginx used as the only reverse proxy entrypoint.

### Port exposure summary (production)

| Port | Backend | Scraper |
|------|---------|---------|
| 22 (SSH) | Public (key-only) | Public (key-only) |
| 80 (HTTP) | Public (nginx) | Closed |
| 443 (HTTPS) | Allowed by UFW (cert pending) | Closed |
| 3000-3002 | Localhost only | Localhost only |
| 5432 | Localhost only | Localhost only |
| 8000 | — | Localhost only |
| 8080 | Localhost only | — |
| 8191 | — | Localhost only |
| 9090 | — | Localhost only |

---

## Deployment Commands

### Production deploy

```bash
bash infra/deploy/deploy.sh backend
bash infra/deploy/deploy.sh scraper
bash infra/deploy/deploy.sh all
```

### Scraper proxy rotation (production)

```bash
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28 '/etc/vacancy-mirror/rotate_webshare_proxy.sh'
```

