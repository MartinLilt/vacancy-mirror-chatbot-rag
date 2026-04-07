# Infrastructure Overview

Last updated: 2026-04-07

## Servers

| Server | IP | Role |
|--------|----|------|
| Backend | `178.104.113.58` | Telegram bot, Stripe webhooks, Chatwoot, Grafana, PostgreSQL |
| Scraper | `178.104.110.28` | Web scraper, FlareSolverr, Prometheus, Grafana, PostgreSQL |

SSH access (key-only, passwords disabled):
```bash
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58   # backend
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28   # scraper
```

---

## Backend Server `178.104.113.58`

### Services

| Service | Type | Status | Port | Access |
|---------|------|--------|------|--------|
| **nginx** | Host (systemd) | Running | `0.0.0.0:80` | Public — reverse proxy for webhooks |
| **backend** (Telegram bot) | Docker | Running | — | Internal only (no port mapping) |
| **support-webhook** (Stripe) | Docker | Running | `127.0.0.1:8080` | Localhost — nginx proxies to it |
| **postgres** (pgvector) | Docker | Running | `127.0.0.1:5432` | Localhost only |
| **grafana-backend** | Docker | Running | `127.0.0.1:3001` | Localhost only |
| **chatwoot-rails** | Docker | Running | `127.0.0.1:3002` | Localhost only |
| **chatwoot-sidekiq** | Docker | Running | — | Internal only |
| **chatwoot-redis** | Docker | Running | — | Internal only |
| **chatwoot-postgres** | Docker | Running | — | Internal only |

### Nginx Configuration (host-level)

Located at `/etc/nginx/sites-enabled/vacancy-mirror`:

- `vacancy-mirror.com /webhook` → `http://127.0.0.1:8080/webhook` (Stripe webhook → support-webhook container)
- `vacancy-mirror.com /pay/` → `http://127.0.0.1:8080` (Stripe pay redirects)
- `vacancy-mirror.com /` → redirect to `https://vacancy-mirror.com` (Vercel)

### Docker Compose

- **File on server:** `/etc/vacancy-mirror/docker-compose.yml`
- **Source:** `infra/deploy/docker-compose.backend.yml`
- **Env file:** `/etc/vacancy-mirror/backend.env`

### Firewall (UFW)

```
Status: active
Default: deny incoming, allow outgoing

22/tcp    ALLOW    Anywhere    # SSH
80/tcp    ALLOW    Anywhere    # HTTP
443/tcp   ALLOW    Anywhere    # HTTPS (reserved for future SSL)
```

---

## Scraper Server `178.104.110.28`

### Services

| Service | Type | Status | Port | Access |
|---------|------|--------|------|--------|
| **scraper** (cron + FastAPI) | Docker | Running | `127.0.0.1:8000` | Localhost only |
| **flaresolverr** | Docker | Running | `127.0.0.1:8191` | Localhost only |
| **postgres** (pgvector) | Docker | Running | `127.0.0.1:5432` | Localhost only |
| **prometheus** | Docker | Running | `127.0.0.1:9090` | Localhost only |
| **grafana** | Docker | Running | `127.0.0.1:3000` | Localhost only |
| **node-exporter** | Docker | Running | — | Internal only (scraped by Prometheus) |

### Docker Compose

- **File on server:** `/etc/vacancy-mirror/docker-compose.yml`
- **Source:** `infra/deploy/docker-compose.server2.yml`
- **Env file:** `/etc/vacancy-mirror/.env`

### Cron Jobs

```
0 2 * * *  /etc/vacancy-mirror/rotate_webshare_proxy.sh  # Daily proxy rotation at 02:00 UTC
```

### Firewall (UFW)

```
Status: active
Default: deny incoming, allow outgoing

22/tcp    ALLOW    Anywhere    # SSH
```

---

## Security Hardening (applied 2026-04-07)

### What was fixed

1. **Squid proxy removed** — was running as open proxy on `*:3128`, allowing anyone to relay traffic through the server. This caused Hetzner abuse tickets.
2. **SSH password authentication disabled** — both servers now accept key-based login only (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`). Backend was receiving ~6200 brute-force attempts per day.
3. **UFW firewall enabled** — default deny-incoming policy on both servers.
4. **All Docker services bound to `127.0.0.1`** — Grafana, Prometheus, FlareSolverr, Scraper API, PostgreSQL are not accessible from the internet.
5. **Docker nginx container removed** — was crash-looping due to port conflict with host nginx and missing SSL certificates. Host nginx handles all reverse proxying.

### Port exposure summary

| Port | Backend | Scraper |
|------|---------|---------|
| 22 (SSH) | ✅ Public (key-only) | ✅ Public (key-only) |
| 80 (HTTP) | ✅ Public (nginx) | ❌ Closed |
| 443 (HTTPS) | ✅ UFW allows (no cert yet) | ❌ Closed |
| 3000-3002 (Grafana/Chatwoot) | 🔒 localhost | 🔒 localhost |
| 5432 (PostgreSQL) | 🔒 localhost | 🔒 localhost |
| 8000 (Scraper API) | — | 🔒 localhost |
| 8080 (Stripe webhook) | 🔒 localhost | — |
| 8191 (FlareSolverr) | — | 🔒 localhost |
| 9090 (Prometheus) | — | 🔒 localhost |

---

## Deployment

### Deploy backend
```bash
bash infra/deploy/deploy.sh backend
```

### Deploy scraper
```bash
bash infra/deploy/deploy.sh scraper
```

### Deploy both
```bash
bash infra/deploy/deploy.sh all
```

### Rotate proxy credentials
```bash
# Runs automatically via cron at 02:00 UTC on scraper server
# Manual trigger:
ssh -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28 '/etc/vacancy-mirror/rotate_webshare_proxy.sh'
```

