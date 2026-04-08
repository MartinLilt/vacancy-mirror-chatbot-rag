# Infrastructure Overview

Last updated: 2026-04-08

## Servers

| Server | IP | Primary Role |
|--------|----|--------------|
| Backend | `178.104.113.58` | Telegram bot, assistant-infer (×3), Stripe/support webhooks, FastAPI, Chatwoot, Grafana, PostgreSQL |
| Scraper | `178.104.110.28` | Scraper (cron + API), FlareSolverr, Prometheus, Grafana, PostgreSQL |

Both servers: **CX23** (2 vCPU / 4 GB RAM), Ubuntu 24.04, Hetzner Nuremberg (`nbg1`).

SSH access (key-only, port **2222**, passwords disabled):
```bash
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58   # backend
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28   # scraper
```

---

## Production Environment

### Backend Server (Production) `178.104.113.58`

#### Services

| Service | Type | Port | Access | Purpose |
|---------|------|------|--------|---------|
| **nginx** | Host (systemd) | `0.0.0.0:80/443` | Public | Reverse proxy → `127.0.0.1:8080` (support-webhook), `127.0.0.1:8000` (api). TLS via Let's Encrypt (`api.vacancy-mirror.com`) |
| **backend** (Telegram bot) | Docker | — | Internal only | Telegram long-polling worker |
| **assistant-infer-1/2/3** | Docker | `8090` (internal) | Internal only | Horizontal assistant inference replicas. Backend load-balances via `ASSISTANT_INFER_URLS` |
| **support-webhook** | Docker | `127.0.0.1:8080` | Localhost only | Stripe webhook + support endpoints |
| **api** | Docker | `127.0.0.1:8000` | Via nginx | FastAPI web API (for frontend) |
| **postgres** (pgvector) | Docker | `127.0.0.1:5432` | Localhost only | Product DB |
| **grafana-backend** | Docker | `127.0.0.1:3001` | Localhost only | Backend monitoring (datasource: PostgreSQL) |
| **chatwoot-rails** | Docker | `127.0.0.1:3002` | Localhost only | Support UI |
| **chatwoot-sidekiq** | Docker | — | Internal only | Chatwoot worker queue |
| **chatwoot-redis** | Docker | — | Internal only | Chatwoot cache/queue store |
| **chatwoot-postgres** | Docker | — | Internal only | Chatwoot DB |

All containers use `security_opt: no-new-privileges`, `cap_drop: ALL`, `read_only: true` (with tmpfs for `/tmp` and `/run`). Postgres gets minimal caps (CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER).

#### Nginx (host-level)

Config source: `infra/deploy/nginx.conf` → deployed to `/etc/vacancy-mirror/nginx.conf`

Routes on `api.vacancy-mirror.com`:
- Port 80 → 301 redirect to HTTPS (+ ACME challenge passthrough)
- `https://…/webhook` → `http://127.0.0.1:8080` (Stripe webhook via support-webhook container)
- `https://…/support/` → `http://127.0.0.1:8080` (support API via support-webhook container)
- `https://…/` → `http://127.0.0.1:8000` (FastAPI via api container)

⚠️ nginx runs on the **host** (systemd), not inside Docker. All upstreams are reached via `127.0.0.1:PORT` (Docker published ports). Do NOT use Docker hostnames or `resolver 127.0.0.11` — Docker embedded DNS is only available inside container network namespaces.

Rate limiting applied via `harden_servers.sh`: `limit_req_zone` 10r/s burst 20, connection limits, security headers (X-Frame-Options, X-Content-Type-Options, server_tokens off).

#### Compose and env (production)

- Compose file on server: `/etc/vacancy-mirror/docker-compose.yml`
- Source in repo: `infra/deploy/docker-compose.backend.yml`
- Env file: `/etc/vacancy-mirror/backend.env`
- Grafana provisioning: `/etc/vacancy-mirror/grafana-backend/provisioning/`

Optional `/start` preview video flags in `backend.env`:
- `START_PREVIEW_VIDEO_ENABLED=1` (set `0` to disable preview without redeploying code)
- `START_PREVIEW_VIDEO_PATH=` (optional override path inside container; default points to bundled asset)

#### Firewall (UFW)

```text
Status: active
Default: deny incoming, allow outgoing

2222/tcp  ALLOW    Anywhere    # SSH
80/tcp    ALLOW    Anywhere    # HTTP nginx
443/tcp   ALLOW    Anywhere    # HTTPS nginx
```

---

### Scraper Server (Production) `178.104.110.28`

#### Services

| Service | Type | Port | Access | Purpose |
|---------|------|------|--------|---------|
| **scraper** | Docker | `127.0.0.1:8000` | Localhost only | supervisord: (1) cron (chaos scraper hourly 8–22 Mon–Sat, proxy usage every 15m), (2) uvicorn scraper_api :8000 |
| **flaresolverr** | Docker | `127.0.0.1:8191` | Localhost only | Cloudflare bypass for scraping |
| **postgres** | Docker | `127.0.0.1:5432` | Localhost only | Scraper DB (raw_jobs, scrape_runs, proxy_usage_snapshots) |
| **prometheus** | Docker | `127.0.0.1:9090` | Localhost only | Metrics collection (scrapes node-exporter + self, 15s interval, 30d retention) |
| **grafana** | Docker | `127.0.0.1:3000` | Localhost only | Scraper monitoring (datasources: Prometheus + PostgreSQL) |
| **node-exporter** | Docker | — | Internal only | Host metrics exporter |

#### Compose and env (scraper)

- Compose file on server: `/etc/vacancy-mirror/docker-compose.yml`
- Source in repo: `infra/deploy/docker-compose.server2.yml`
- Env file: `/etc/vacancy-mirror/.env`
- Grafana provisioning: `/etc/vacancy-mirror/grafana/provisioning/`
- Prometheus config: `/etc/vacancy-mirror/prometheus.yml`

#### Cron (host-level)

```text
0 2 * * *  /etc/vacancy-mirror/rotate_webshare_proxy.sh   # daily proxy credential rotation
```

#### Firewall (UFW)

```text
Status: active
Default: deny incoming, allow outgoing

2222/tcp  ALLOW    Anywhere    # SSH
```

---

## Security Hardening (applied 2026-04-07)

Applied via `infra/deploy/harden_servers.sh`, then `nuke_and_redeploy.sh` for clean re-deploy.

### What was done

1. **Squid open proxy removed** — `*:3128` was exposed publicly; package purged.
2. **SSH hardened** — Port moved to **2222**, password auth disabled, key-only (`PermitRootLogin prohibit-password`), MaxAuthTries 3, X11 disabled, idle timeout 10 min.
3. **UFW firewall** — Default deny incoming. Backend: 2222 + 80 + 443. Scraper: 2222 only.
4. **fail2ban** — Enabled on sshd port 2222. 3 retries → 2-hour ban, 10-min find window.
5. **Unattended security upgrades** — Automatic daily security patches (no auto-reboot).
6. **auditd** — Monitoring: `/etc/passwd`, `/etc/shadow`, `/etc/ssh/sshd_config`, `/etc/vacancy-mirror/`, docker socket/binary, user management, cron files.
7. **Suspicious packages removed** — squid, telnetd, rpcbind, avahi-daemon, cups purged; scan for executables in `/tmp`, `/var/tmp`, `/dev/shm`.
8. **File permissions** — Env files `chmod 600`, vacancy-mirror dir `chmod 700`, docker socket `chmod 660`.
9. **Nginx rate limiting** (backend) — `limit_req_zone` 10r/s burst 20, connection limits, security headers.
10. **Docker container hardening** — All containers: `no-new-privileges`, `cap_drop: ALL`, `read_only: true` (where applicable). All ports bound to `127.0.0.1`.
11. **Full nuke & redeploy** — All containers/images/networks/cache destroyed, fresh images pulled from GHCR. Named volumes (postgres-data, grafana-data) preserved. Fresh env files uploaded.

### Network Isolation (applied 2026-04-08)

Applied via `infra/deploy/lockdown_network.sh`. Defense-in-depth against Docker-bypasses-UFW and container-downloads-malware threats.

#### Docker daemon (`/etc/docker/daemon.json`)
- **`userland-proxy: false`** — Docker uses iptables NAT instead of `docker-proxy` processes. Without this, `docker-proxy` listens on published ports and bypasses all iptables rules.
- **`no-new-privileges: true`** — Enforced by daemon for all containers.
- **`live-restore: true`** — Containers survive daemon restarts.
- **Log limits** — 10MB × 3 files per container (prevents disk exhaustion).

#### DOCKER-USER iptables chain (blocks external → container, IPv4 + IPv6)
Docker inserts its own rules in iptables FORWARD chain, bypassing UFW's INPUT chain. The DOCKER-USER chain is the only place where custom rules are respected by Docker. Rules are applied to both `iptables` (IPv4) and `ip6tables` (IPv6) to prevent bypass:
- Allow established/related connections (return traffic)
- Allow loopback (host → container via `127.0.0.1` published ports)
- Allow Docker inter-container traffic (172.16.0.0/12 ↔ 172.16.0.0/12)
- Allow container → internet only on ports **443, 80, 587, 53** (HTTPS, HTTP, SMTP, DNS)
- **DROP + LOG everything else** (external→container inbound, container→weird ports)

#### Docker internal networks
Containers that don't need internet are on `internal: true` networks (physically no route to internet):

| Server | Container | Networks | Internet |
|--------|-----------|----------|----------|
| Backend | postgres | `internal` | ❌ Blocked |
| Backend | grafana-backend | `internal` | ❌ Blocked |
| Backend | backend | `internal` + `egress` | ✅ 443/80/587/53 only |
| Backend | assistant-infer-1/2/3 | `internal` + `egress` | ✅ 443/80/587/53 only |
| Backend | support-webhook | `internal` + `egress` | ✅ 443/80/587/53 only |
| Backend | api | `internal` + `egress` | ✅ 443/80/587/53 only |
| Scraper | postgres | `internal` | ❌ Blocked |
| Scraper | prometheus | `internal` | ❌ Blocked |
| Scraper | node-exporter | `internal` | ❌ Blocked |
| Scraper | grafana | `internal` | ❌ Blocked |
| Scraper | scraper | `internal` + `egress` | ✅ 443/80/587/53 only |
| Scraper | flaresolverr | `internal` + `egress` | ✅ 443/80/587/53 only |

#### Security layers (defense in depth)

```
Layer 1: UFW                  — deny incoming (except SSH 2222 + nginx 80/443)
Layer 2: DOCKER-USER iptables — block external→container forwarding (IPv4 + IPv6)
Layer 3: userland-proxy=false — no iptables-bypassing docker-proxy processes
Layer 4: internal networks    — postgres/grafana/prometheus physically can't reach internet
Layer 5: outbound port limit  — containers limited to ports 443/80/587/53 only
Layer 6: container hardening  — read_only, no-new-privileges, cap_drop ALL
```

### Port exposure summary (production)

| Port | Backend | Scraper |
|------|---------|---------|
| 2222 (SSH) | Public (key-only, fail2ban) | Public (key-only, fail2ban) |
| 80 (HTTP) | Public (nginx → redirect to HTTPS) | Closed |
| 443 (HTTPS) | Public (nginx → api/webhooks) | Closed |
| 3000-3002 | Localhost only | Localhost only |
| 5432 | Localhost only | Localhost only |
| 8000 | Localhost only (nginx → api) | Localhost only |
| 8080 | Localhost only | — |
| 8090 | Internal (assistant-infer) | — |
| 8191 | — | Localhost only |
| 9090 | — | Localhost only |

---

## Deployment Commands

### Normal deploy (build → push → restart)

```bash
# One-command: build, push to GHCR, restart on server
bash ship.sh backend              # backend only
bash ship.sh scraper              # scraper only
bash ship.sh all                  # everything
bash ship.sh backend --no-cache   # force full rebuild

# Or separately:
bash infra/deploy/push-images.sh backend    # build + push image
bash infra/deploy/deploy.sh backend         # pull + restart on server
bash infra/deploy/deploy.sh scraper
bash infra/deploy/deploy.sh all
```

### Incident response (nuke & redeploy)

```bash
# Full wipe: destroy all containers/images, upload fresh env + compose, redeploy
bash infra/deploy/nuke_and_redeploy.sh backend
bash infra/deploy/nuke_and_redeploy.sh scraper
bash infra/deploy/nuke_and_redeploy.sh all
```

⚠️ Preserves Docker named volumes (DB data, Grafana data). Destroys all containers, images, networks, build cache.

### Security hardening

```bash
bash infra/deploy/harden_servers.sh backend
bash infra/deploy/harden_servers.sh scraper
bash infra/deploy/harden_servers.sh all
```

⚠️ After running, SSH port changes to 2222.

### Network lockdown (Docker isolation + iptables)

```bash
# Audit only (check what's exposed, no changes)
bash infra/deploy/lockdown_network.sh audit both

# Apply fixes (Docker daemon, iptables DOCKER-USER, internal networks)
bash infra/deploy/lockdown_network.sh fix both

# Audit + fix + verify
bash infra/deploy/lockdown_network.sh all both
```

⚠️ Restarts Docker daemon and all containers. Containers on `internal` network lose internet access.

### SSL certificate

```bash
bash infra/deploy/setup-ssl.sh    # one-time Let's Encrypt cert for api.vacancy-mirror.com
```

### Scraper proxy rotation

```bash
# Runs daily at 02:00 UTC via cron on scraper server
# Manual trigger:
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28 '/etc/vacancy-mirror/rotate_webshare_proxy.sh'
```

---

## Database Schema

Both servers run independent PostgreSQL (pgvector) instances with the same schema.

| Table | Purpose |
|-------|---------|
| `scrape_runs` | Audit log of every scraper execution (status, pages, jobs stats, errors) |
| `raw_jobs` | Raw Upwork job postings (title, description, skills[], budget, client info, ciphertext). Unique by (category_uid, job_uid) |
| `profiles` | Named role profiles per category/cluster (role_name, demand_type: broad/niche/exotic, demand_ratio) |
| `profile_embeddings` | vector(1024) embeddings (BAAI/bge-large-en-v1.5) for RAG semantic search. IVFFlat index |
| `job_samples` | Individual job postings linked to a profile (RAG context) |
| `subscriptions` | Telegram user → Stripe subscription (plan: free/plus/pro_plus, status: active/cancelled/past_due) |
| `proxy_usage_snapshots` | Webshare proxy usage telemetry (requests, bytes, raw JSON) |
| `support_feedback_events` | Contact Support submissions from Telegram (user info, message, reply channel, status, Chatwoot link) |
| `support_replies` | Operator reply delivery log (channel: telegram/email, source: support_api/chatwoot, status: sent/failed) |

Extension: `pgvector` (vector similarity search).

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
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58
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

## Known Issues & TODO

1. ~~`rotate_webshare_proxy.sh` has a hardcoded API key`~~ — **FIXED** (2026-04-08). Now sources `WEBSHARE_API_KEY` from `/etc/vacancy-mirror/.env`.
2. ~~`setup-ssl.sh` missing `-p 2222`~~ — **FIXED** (2026-04-08). Uses `SSH_PORT` env var (default 2222).
3. ~~No certbot auto-renewal~~ — **FIXED** (2026-04-08). `setup-ssl.sh` now installs a cron job (`0 3,15 * * * certbot renew`) with pre/post hooks to stop/start nginx.
4. ~~`docker-compose.server1.yml` is legacy~~ — **Marked deprecated** (2026-04-08). Header says "DO NOT deploy — use `docker-compose.backend.yml`".
5. **Two independent Postgres instances** — no replication. Scraper data is accessed via `scraper_api` HTTP endpoint from backend. This is by design (isolation), not a bug.
