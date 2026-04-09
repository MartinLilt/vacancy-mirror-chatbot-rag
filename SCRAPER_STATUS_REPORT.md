# Scraper Server Infrastructure Status Report
**Generated:** April 9, 2026  
**Scraper Server IP:** 178.104.110.28  
**Backend Server IP:** 178.104.113.58

---

## Executive Summary

The scraper infrastructure consists of two production servers running containerized services:

1. **Scraper Server (178.104.110.28)** - Dedicated to web scraping operations
2. **Backend Server (178.104.113.58)** - Telegram bot, API, and assistant inference

---

## Scraper Server Architecture (178.104.110.28)

### Running Services

The scraper server runs **6 containerized services** managed by Docker Compose:

| Service | Container Name | Image | Ports | Networks | Status |
|---------|----------------|-------|-------|----------|--------|
| **postgres** | - | pgvector/pgvector:pg16 | 127.0.0.1:5432 | internal | Persistent DB |
| **flaresolverr** | flaresolverr | ghcr.io/flaresolverr/flaresolverr:latest | 127.0.0.1:8191 | internal, egress | Cloudflare bypass |
| **scraper** | scraper | ghcr.io/martinlilt/vacancy-mirror-scraper:latest | 127.0.0.1:8000 | internal, egress | Main scraper + API |
| **prometheus** | prometheus | prom/prometheus:latest | 127.0.0.1:9090 | internal | Metrics collection |
| **node-exporter** | node-exporter | prom/node-exporter:latest | - | internal | System metrics |
| **grafana** | grafana | grafana/grafana:latest | 127.0.0.1:3000 | internal | Monitoring UI |

### Network Architecture

**Two isolated networks:**

1. **internal** (no internet access)
   - postgres
   - prometheus
   - node-exporter
   - grafana (visualization only)

2. **egress** (internet access)
   - scraper (needs Upwork access)
   - flaresolverr (needs Cloudflare challenge solving)

### Scraper Container Details

The scraper container runs **two processes** via supervisord:

1. **cron** - Scheduled scraping jobs
   - Fires every hour 8:00-22:00, Mon-Sat
   - Random 0-10 min delay before starting
   - Logs to `/var/log/scraper.log`

2. **scraper-api** (uvicorn) - FastAPI server on port 8000
   - Endpoint: POST `/scrape`
   - Endpoint: POST `/jobs/clear`
   - Authentication via `SCRAPER_API_KEY`

### Cron Schedule

```cron
# Main scraper - hourly during work hours
0 8-22 * * 1-6 /app/scripts/chaos_runner.sh >> /var/log/scraper.log 2>&1

# Proxy usage collection - every 15 minutes
*/15 * * * * /bin/bash /app/scripts/collect_proxy_usage_runner.sh >> /var/log/scraper.log 2>&1
```

### Proxy Configuration

**Two separate proxy channels:**

- **PROXY_URL** → Used by scraper Chrome (nodriver)
- **FLARESOLVERR_PROXY_URL** → Used by FlareSolverr

**Timeout handling knobs:**
- `FLARESOLVERR_MAX_TIMEOUT_MS=120000`
- `FLARESOLVERR_TIMEOUT_COOLDOWN_SEC=35`
- `FLARESOLVERR_TIMEOUT_BACKOFF_MULT=1.8`
- `FLARESOLVERR_ROTATE_AFTER_TIMEOUTS=999`

### Persistent Storage

Volumes mounted:
- `postgres-data` → PostgreSQL database
- `scraper-data` → `/app/data` (Chrome profile, cookies, state)
- `prometheus-data` → Metrics storage
- `grafana-data` → Grafana configuration

---

## Backend Server Architecture (178.104.113.58)

### Running Services

The backend server runs **7 containerized services**:

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| **postgres** | pgvector/pgvector:pg16 | 127.0.0.1:5432 | Database |
| **backend** | ghcr.io/[user]/vacancy-mirror-backend:latest | - | Telegram bot |
| **assistant-infer-1** | ghcr.io/[user]/vacancy-mirror-backend:latest | 8090 | Inference worker 1 |
| **assistant-infer-2** | ghcr.io/[user]/vacancy-mirror-backend:latest | 8090 | Inference worker 2 |
| **assistant-infer-3** | ghcr.io/[user]/vacancy-mirror-backend:latest | 8090 | Inference worker 3 |
| **support-webhook** | ghcr.io/[user]/vacancy-mirror-backend:latest | 127.0.0.1:8080 | Stripe webhooks |
| **api** | ghcr.io/[user]/vacancy-mirror-api:latest | 127.0.0.1:8000 | FastAPI web service |
| **grafana-backend** | grafana/grafana:latest | 127.0.0.1:3001 | Backend monitoring |

### Assistant Inference Scaling

**Current configuration:**
- 3 horizontal replicas for assistant inference
- Round-robin load balancing with failover
- Fallback to local orchestrator if all replicas fail
- Metrics available via `/assistant_metrics` command

**Environment variables:**
```env
ASSISTANT_INFER_URLS=http://assistant-infer-1:8090,http://assistant-infer-2:8090,http://assistant-infer-3:8090
ASSISTANT_REMOTE_TIMEOUT_SEC=70
ASSISTANT_INFER_MAX_CONCURRENCY=24
ASSISTANT_GLOBAL_CONCURRENCY=64
```

---

## Security Hardening

### SSH Configuration
- **Port:** 2222 (non-standard)
- **Authentication:** Key-only (password auth disabled)
- **Root login:** prohibit-password only
- **Max auth tries:** 3
- **X11 forwarding:** disabled

### Firewall (UFW)

**Backend server (178.104.113.58):**
- Port 2222/tcp (SSH)
- Port 80/tcp (HTTP nginx)
- Port 443/tcp (HTTPS nginx)
- Default: deny incoming, allow outgoing

**Scraper server (178.104.110.28):**
- Port 2222/tcp (SSH only)
- Default: deny incoming, allow outgoing

### fail2ban
- Enabled on both servers
- Ban time: 3600 seconds
- Max retries: 3 within 600 seconds
- SSH protection on port 2222

### Container Security
- `security_opt: no-new-privileges:true`
- `cap_drop: ALL` (capabilities dropped)
- `read_only: true` (where applicable)
- Dedicated internal/egress networks

### Audit Logging (auditd)
Monitors changes to:
- `/etc/passwd`, `/etc/shadow`
- `/etc/ssh/sshd_config`
- `/etc/vacancy-mirror/`
- Cron files
- Docker commands

---

## Monitoring & Observability

### Prometheus Metrics

**Scrape targets:**
- node-exporter (system metrics)
- prometheus (self-monitoring)

**Retention:** 30 days

**Access:**
```bash
# Scraper server Grafana (port 3000)
ssh -N -L 3000:127.0.0.1:3000 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28

# Backend server Grafana (port 3001)
ssh -N -L 3001:127.0.0.1:3001 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58
```

### Log Locations

**Scraper container:**
- `/var/log/scraper.log` (cron jobs output)
- `docker logs scraper` (supervisor/API output)
- `docker logs flaresolverr` (Cloudflare bypass logs)

**Backend container:**
- `docker compose logs backend`
- `docker compose logs assistant-infer-1/2/3`
- `docker compose logs support-webhook`

---

## Resource Consumption

### Server Specifications
- **Type:** Hetzner cx23
- **Location:** Nuremberg (nbg1)
- **OS:** Ubuntu 24.04

### Volume Usage

**Scraper server:**
- `postgres-data` → Job storage
- `scraper-data` → Chrome session data
- `prometheus-data` → Time-series metrics (30-day retention)
- `grafana-data` → Dashboard configs

**Backend server:**
- `postgres-data` → User data, conversations, embeddings
- `grafana-backend-data` → Backend monitoring dashboards

### Proxy Telemetry

**Real usage tracking:**
- Source: Webshare API
- Collection: Every 15 minutes (cron)
- Storage: `proxy_usage_snapshots` table
- Visualization: Grafana panel "Residential Proxy Usage (MB/h, real)"

---

## Health Check Commands

### Scraper Server Health

```bash
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28

# Check all containers
cd /etc/vacancy-mirror
docker compose ps

# Verify FlareSolverr
docker exec flaresolverr env | grep PROXY_URL
curl -s http://localhost:8191/health

# Verify scraper
docker exec scraper env | grep -E 'PROXY_URL|FLARESOLVERR_PROXY_URL|FLARESOLVERR_MAX_TIMEOUT_MS'
docker exec scraper python3 -c 'import scraper; print("ok")'

# Check logs
docker exec scraper tail -f /var/log/scraper.log
docker logs -f flaresolverr

# Manual scraper run
docker exec scraper /app/scripts/chaos_runner.sh
```

### Backend Server Health

```bash
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58

cd /etc/vacancy-mirror
docker compose ps backend support-webhook assistant-infer-1 assistant-infer-2 assistant-infer-3

docker compose logs backend --tail 30
docker compose logs assistant-infer-1 --tail 20
docker compose logs assistant-infer-2 --tail 20
docker compose logs assistant-infer-3 --tail 20
```

---

## Deployment Procedures

### Build & Deploy (from local machine)

**Backend:**
```bash
bash ship.sh backend
```

**Scraper:**
```bash
bash ship.sh scraper
```

### Manual Deploy Steps

**Backend:**
```bash
bash infra/deploy/push-images.sh backend
bash infra/deploy/deploy.sh backend
```

**Scraper:**
```bash
bash infra/deploy/push-images.sh scraper
bash infra/deploy/deploy.sh scraper
```

### Important Notes

- **Apple Silicon warning:** Must build with `--platform linux/amd64`
- `ship.sh` handles cross-platform builds automatically
- Environment changes require `--force-recreate`, not just `restart`

### Environment File Locations

**Scraper server:**
- `/etc/vacancy-mirror/.env`
- `/etc/vacancy-mirror/docker-compose.yml`

**Backend server:**
- `/etc/vacancy-mirror/backend.env`
- `/etc/vacancy-mirror/docker-compose.yml`

---

## Known Issues & Runbooks

### Issue: FlareSolverr Timeout

**Symptoms:**
- `FlareSolverr HTTP error 500 ... Timeout after 120.0 seconds`
- Repeated "Error solving the challenge"

**Resolution:**
1. Check proxy env vars in both containers
2. Verify sticky proxy in `/etc/vacancy-mirror/.env`
3. Recreate services:
   ```bash
   docker compose up -d --no-deps --force-recreate flaresolverr scraper
   ```
4. Test FlareSolverr: `curl -s http://localhost:8191/health`

### Issue: Backend Infer Replicas Failing

**Symptoms:**
- `invalid choice: 'assistant-infer'`
- `exec /usr/local/bin/python: exec format error`

**Resolution:**
- Old image without CLI command → Rebuild & push backend
- Wrong architecture (arm64 vs amd64) → Use `ship.sh` instead of plain `docker build`

### Issue: Scraper Not Running

**Check:**
1. Cron status: `docker exec scraper crontab -l`
2. Supervisor processes: `docker exec scraper supervisorctl status`
3. Manual run: `docker exec scraper /app/scripts/chaos_runner.sh`
4. Database connection: Check `DATABASE_URL` in container env

---

## System Boundaries (Critical)

**Separation of concerns:**
- Backend server (178.104.113.58) → Telegram bot, RAG, API, inference
- Scraper server (178.104.110.28) → Web scraping, Cloudflare bypass, job ingestion

**Do NOT:**
- Mix backend and scraper code changes
- Modify backend to fix scraper proxy issues
- Assume restart reloads env (use recreate)

**DO:**
- Treat as separate systems
- Validate server-side before claiming fix
- Check which server an issue belongs to first

---

## Quick Reference

### SSH Access
```bash
# Scraper server
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28

# Backend server
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58
```

### Port Tunneling
```bash
# Scraper Grafana
ssh -N -L 3000:127.0.0.1:3000 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28

# Backend Grafana
ssh -N -L 3001:127.0.0.1:3001 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58

# Scraper Prometheus
ssh -N -L 9090:127.0.0.1:9090 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
```

### Container Locations
```bash
# All configs
/etc/vacancy-mirror/

# Compose file
/etc/vacancy-mirror/docker-compose.yml

# Environment
/etc/vacancy-mirror/.env (scraper)
/etc/vacancy-mirror/backend.env (backend)

# Database init
/etc/vacancy-mirror/db/init.sql

# Monitoring
/etc/vacancy-mirror/prometheus.yml
/etc/vacancy-mirror/grafana/provisioning/
```

---

## Consumption Summary

### Network Traffic
- **Proxy usage:** Tracked via Webshare API every 15 minutes
- **Residential proxy:** Split between scraper Chrome and FlareSolverr
- **Monitoring:** Real-time in Grafana dashboard

### Storage
- **PostgreSQL:** Two separate instances (backend DB + scraper DB)
- **Prometheus:** 30-day retention of metrics
- **Grafana:** Dashboard configurations
- **Scraper data:** Chrome profiles, cookies, session state

### Compute
- **Scraper:** Chromium browser + nodriver automation
- **FlareSolverr:** Chromium for Cloudflare bypass
- **Backend:** 3x inference replicas + main bot process
- **Monitoring:** Prometheus + node-exporter + Grafana (2 instances)

---

## Next Steps / Recommendations

1. **Set up monitoring alerts** for critical metrics:
   - Container restart count
   - Scraper success rate
   - FlareSolverr timeout frequency
   - Database connection failures

2. **Regular maintenance tasks:**
   - Review auditd logs weekly
   - Check fail2ban ban list
   - Monitor disk usage (PostgreSQL, Prometheus)
   - Verify backup procedures

3. **Performance optimization:**
   - Review assistant-infer concurrency settings
   - Analyze proxy usage patterns
   - Optimize scraper scheduling based on load

4. **Security enhancements:**
   - Regular security updates (unattended-upgrades enabled)
   - Review UFW rules periodically
   - Rotate SSH keys quarterly

---

**Report End**

