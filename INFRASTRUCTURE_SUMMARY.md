# Infrastructure Quick Summary

## 🎯 Overview
Two-server architecture for Upwork job scraping and Telegram bot services.

---

## 📍 Servers

### Backend Server: **178.104.113.58**
- **Purpose:** Telegram bot, RAG/AI assistant, API services
- **Access:** `ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58`
- **Key Services:**
  - Backend (Telegram bot)
  - 3x Assistant Inference replicas (horizontal scaling)
  - Support webhook (Stripe)
  - API (FastAPI)
  - Grafana (port 3001)
  - PostgreSQL

### Scraper Server: **178.104.110.28**
- **Purpose:** Web scraping, Cloudflare bypass, job collection
- **Access:** `ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28`
- **Key Services:**
  - Scraper (cron + API on port 8000)
  - FlareSolverr (Cloudflare bypass on port 8191)
  - PostgreSQL (local)
  - Grafana (port 3000)
  - Prometheus + Node Exporter

---

## 🔄 Scraper Operations

### Automatic Schedule
```
Hourly: 8:00-22:00, Monday-Saturday
Random 0-10 min delay before each run
Proxy usage collection: every 15 minutes
```

### Manual Control

**Start scraper manually:**
```bash
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28
docker exec scraper /app/scripts/chaos_runner.sh
```

**Check status:**
```bash
docker compose ps
docker exec scraper tail -f /var/log/scraper.log
```

**API endpoints (requires SCRAPER_API_KEY):**
- `GET /health` - Health check
- `GET /status` - Current scraper status
- `POST /scrape` - Trigger manual scrape
- `POST /scrape-chaos` - Trigger chaos mode (all categories)
- `POST /stop` - Stop running scraper
- `GET /logs` - View recent logs
- `GET /chaos-state` - Progress per category
- `GET /schedule` - View cron schedule
- `POST /schedule` - Update schedule
- `POST /schedule/enable` - Enable auto-scraping
- `POST /schedule/disable` - Disable auto-scraping

---

## 📊 Monitoring

### Grafana Access
```bash
# Scraper monitoring (Prometheus + system metrics)
ssh -N -L 3000:127.0.0.1:3000 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
# Then open: http://localhost:3000

# Backend monitoring (PostgreSQL + services)
ssh -N -L 3001:127.0.0.1:3001 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58
# Then open: http://localhost:3001
```

### Key Metrics
- System resources (CPU, RAM, disk)
- Scraper success/failure rates
- Proxy usage (real-time from Webshare API)
- FlareSolverr timeout frequency
- Assistant inference request distribution
- Database connection pool status

---

## 🔐 Security

### Hardening Applied
✅ SSH on port 2222 (non-standard)  
✅ Key-only authentication  
✅ UFW firewall (deny all incoming except SSH + HTTP/HTTPS on backend)  
✅ fail2ban active (3 tries, 1-hour ban)  
✅ Container isolation (internal/egress networks)  
✅ Read-only containers where possible  
✅ Capabilities dropped (cap_drop: ALL)  
✅ Audit logging (auditd) for sensitive files  
✅ Auto security updates enabled  

### Ports Exposed
**Backend:** 80, 443 (nginx), 2222 (SSH)  
**Scraper:** 2222 (SSH only)  

All service ports (5432, 8000, 8080, 8191, 3000, 3001, 9090) bound to **127.0.0.1** only.

---

## 🚀 Deployment

### Quick Deploy
```bash
# Backend
bash ship.sh backend

# Scraper
bash ship.sh scraper
```

### Manual Steps
```bash
# Build + push images
bash infra/deploy/push-images.sh backend  # or scraper
bash infra/deploy/deploy.sh backend       # or scraper
```

**Important:** `ship.sh` builds for `linux/amd64` (required for Apple Silicon Macs)

### Verify Deployment
```bash
# Backend
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58
cd /etc/vacancy-mirror
docker compose ps
docker compose logs backend --tail 20
docker compose logs assistant-infer-1 --tail 20

# Scraper
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28
cd /etc/vacancy-mirror
docker compose ps
docker exec scraper python3 -c 'import scraper; print("ok")'
```

---

## 🔧 Troubleshooting

### Scraper Issues

**FlareSolverr timeouts:**
```bash
# Check proxy configuration
docker exec flaresolverr env | grep PROXY_URL
docker exec scraper env | grep -E 'PROXY_URL|FLARESOLVERR_PROXY_URL'

# Verify FlareSolverr health
curl -s http://localhost:8191/health

# Recreate services with new config
cd /etc/vacancy-mirror
docker compose up -d --no-deps --force-recreate flaresolverr scraper
```

**Scraper not collecting jobs:**
```bash
# Check logs
docker exec scraper tail -100 /var/log/scraper.log
docker logs flaresolverr --tail 50

# Check chaos state
curl http://localhost:8000/chaos-state

# Manual run with verbose output
docker exec -it scraper /app/scripts/chaos_runner.sh
```

### Backend Issues

**Assistant inference failures:**
```bash
# Check replica status
docker compose ps assistant-infer-1 assistant-infer-2 assistant-infer-3

# Check logs for errors
docker compose logs assistant-infer-1 --tail 50
docker compose logs assistant-infer-2 --tail 50
docker compose logs assistant-infer-3 --tail 50

# Test health endpoints
docker exec backend curl http://assistant-infer-1:8090/health
```

**Common deploy errors:**
- `invalid choice: 'assistant-infer'` → Old backend image, rebuild
- `exec format error` → Wrong architecture, use `ship.sh`

---

## 📝 Configuration Files

### Scraper Server
```
/etc/vacancy-mirror/
├── .env                           # Environment variables
├── docker-compose.yml             # Service definitions
├── db/init.sql                    # Database schema
├── prometheus.yml                 # Metrics config
└── grafana/provisioning/          # Dashboards
```

### Backend Server
```
/etc/vacancy-mirror/
├── backend.env                    # Environment variables
├── docker-compose.yml             # Service definitions
├── nginx.conf                     # Reverse proxy config
├── db/init.sql                    # Database schema
├── secrets/google_service_account.json
├── assets/send_video.mp4
└── grafana-backend/provisioning/  # Dashboards
```

---

## 🎓 Key Concepts

### Proxy Strategy
- **PROXY_URL** → Chrome browser (nodriver scraping)
- **FLARESOLVERR_PROXY_URL** → FlareSolverr (Cloudflare bypass)
- Two separate proxies for isolation and resilience

### Network Isolation
- **internal** network → No internet (postgres, grafana, prometheus)
- **egress** network → Internet access (scraper, backend, flaresolverr)

### Scraper Modes
- **Chaos mode** → All categories, distributed across available pages
- **Single category** → Target specific category with max pages
- **Cron automatic** → Hourly chaos runs during work hours

### Assistant Scaling
- **3 horizontal replicas** for inference workload
- **Round-robin + failover** for load distribution
- **Local fallback** if all replicas unavailable

---

## 📚 Related Documentation
- **Full Status Report:** `SCRAPER_STATUS_REPORT.md`
- **Infrastructure Details:** `infra/INFRASTRUCTURE.md`
- **Main README:** `README.md`

---

## ⚡ Quick Commands Cheatsheet

```bash
# === SCRAPER SERVER ===

# SSH access
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.110.28

# Status check
cd /etc/vacancy-mirror && docker compose ps

# Manual scrape
docker exec scraper /app/scripts/chaos_runner.sh

# Live logs
docker exec scraper tail -f /var/log/scraper.log

# Recreate after config change
docker compose up -d --no-deps --force-recreate scraper flaresolverr

# === BACKEND SERVER ===

# SSH access
ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@178.104.113.58

# Status check
cd /etc/vacancy-mirror && docker compose ps

# Service logs
docker compose logs backend --tail 30
docker compose logs assistant-infer-1 --tail 20

# Restart specific service
docker compose restart backend

# === DEPLOYMENT (from local machine) ===

# Full deploy
bash ship.sh backend   # or scraper

# Just rebuild images
bash infra/deploy/push-images.sh backend

# Just redeploy (pull + restart)
bash infra/deploy/deploy.sh backend

# === MONITORING ===

# Tunnel Grafana
ssh -N -L 3000:127.0.0.1:3000 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28

# Check Prometheus
ssh -N -L 9090:127.0.0.1:9090 -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
```

---

**Last Updated:** April 9, 2026

