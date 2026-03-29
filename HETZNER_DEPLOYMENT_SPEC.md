# Vacancy Mirror RAG Pipeline — Hetzner Deployment Specification

**Дата создания:** 27 March 2026  
**Версия:** 3.0  
**Язык:** English (для ChatGPT)

---

## 📋 SYSTEM OVERVIEW

The Vacancy Mirror RAG Pipeline is a distributed data pipeline deployed
across two types of containers on Hetzner Cloud:

1. **Scraper containers** — headless Chrome + nodriver, one or more
   instances depending on category load level (L1–L4)
2. **Backend container** — all business logic, AI/ML, API and bot layers

The system scrapes Upwork job vacancies, processes them through
NLP normalization, embedding, clustering and AI profiling, and serves
results to users via a Telegram bot.

**Runtime:** continuous (scrapers run on schedule, backend is always-on)  
**Frequency:** weekly full scrape cycle per category

---

## 🏗️ TWO-CONTAINER ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        HETZNER CLOUD                            │
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────┐              │
│  │  SCRAPER NODE    │        │  SCRAPER NODE     │  (L4 only)  │
│  │  CPX11 (~€5/mo)  │        │  CPX11 (~€5/mo)  │             │
│  │                  │        │                  │              │
│  │  [scraper]       │        │  [scraper]        │             │
│  │  container       │        │  container        │             │
│  └────────┬─────────┘        └────────┬──────────┘             │
│           │  Private Network (10.0.0.x)│                        │
│           └──────────────┬────────────┘                        │
│                          │                                      │
│  ┌───────────────────────▼─────────────────────────────────┐   │
│  │                  BACKEND NODE  CPX32 (~€9/mo)            │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │               [backend] container                │   │   │
│  │  │                                                  │   │   │
│  │  │  1. micro-scraper     — category load table      │   │   │
│  │  │  2. progress DB       — receives scraper results │   │   │
│  │  │  3. normalizer        — NLP + embedding layer    │   │   │
│  │  │  4. clustering        — semantic cores           │   │   │
│  │  │  5. AI assistant      — OpenAI orchestrator      │   │   │
│  │  │  6. Telegram bot      — user-facing chat         │   │   │
│  │  │  7. business logic    — API + coordination       │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │           [postgres] container                   │    │   │
│  │  │           pgvector/pgvector:pg16                 │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 CONTAINER 1: SCRAPER

### Purpose

Runs headless Chrome via `nodriver` to scrape Upwork vacancies.
Stateless — can be spun up/down on demand or scaled horizontally for
Level 4 categories.

### Scaling rules (by category load level)

| Level | total_jobs | Strategy                             | Replicas |
| ----- | ---------- | ------------------------------------ | -------- |
| 🟢 L1 | ≤ 2,500    | max_pages=50, single pass            | 1        |
| 🟡 L2 | ≤ 5,000    | max_pages=100, single pass           | 1        |
| 🟠 L3 | ≤ 25,000   | max_pages=100 + URL filter splits    | 1        |
| 🔴 L4 | > 25,000   | max_pages=100 + splits + k8s replica | **2**    |

**Current category classification:**

```
 #  Lvl  Icon  Total jobs  max_pages  Splits  +Replica  Category
----------------------------------------------------------------
 1  L1   🟢        2,167         50      no        no  Legal
 2  L1   🟢        2,070         50      no        no  Translation
 3  L2   🟡        4,969        100      no        no  Writing
 4  L2   🟡        4,290        100      no        no  Data Science & Analytics
 5  L2   🟡        3,233        100      no        no  Customer Service
 6  L2   🟡        3,072        100      no        no  IT & Networking
 7  L3   🟠       12,648        100     yes        no  Admin Support
 8  L3   🟠        7,809        100     yes        no  Accounting & Consulting
 9  L3   🟠        7,209        100     yes        no  Engineering & Architecture
10  L4   🔴       40,764        100     yes       yes  Design & Creative
11  L4   🔴       32,043        100     yes       yes  Sales & Marketing
12  L4   🔴       31,929        100     yes       yes  Web, Mobile & Software Dev
```

> This table is regenerated weekly by the **micro-scraper** layer
> (backend component #1) and used to decide how many scraper
> containers to start.

### Resources (per instance)

```yaml
Image: Dockerfile.scraper
Memory: 2 GB (Chrome headless)
CPU: 1.5 cores
Restart: no (on-demand)
Network: hetzner-private (10.0.0.x)
Env:
  DB_URL: postgresql://app:${DB_PASSWORD}@backend:5432/vacancy_mirror
  LOG_LEVEL: INFO
```

---

## 📦 CONTAINER 2: BACKEND

### Purpose

Always-on container running all 7 backend layers. Receives scraped
data from scraper containers, processes it and serves the Telegram bot.

### Backend layers

#### Layer 1 — Micro-Scraper (category load monitor)

- Runs `CategoryScraperService` weekly (headless Chrome)
- Produces the category load table (L1–L4 classification)
- Decides how many scraper container replicas to launch
- Writes updated `total_jobs` + level info to PostgreSQL

#### Layer 2 — Progress DB (scraper result ingestion)

- PostgreSQL (pgvector) receives raw vacancy JSON from all scraper
  containers over the private network
- Current schema: `raw_jobs`, `scrape_runs` tables
- Acts as the single source of truth for all downstream layers
- ⚠️ Schema will be revised to support multi-scraper ingestion
  (current schema was designed for single-scraper flow)

#### Layer 3 — Normalizer + Embedding

- Reads raw jobs from DB
- Applies NLP normalization (regex, text cleaning)
- Generates 384-dim embeddings via `BAAI/bge-small-en-v1.5`
- Writes to `pattern_normalized_jobs` + `job_embeddings` tables

#### Layer 4 — Clustering + Semantic Cores

- Runs `NearestNeighbors` (cosine, radius=0.06) on embeddings
- Groups similar jobs into clusters
- Extracts semantic keyword cores per cluster
- Writes to `job_clusters` table

#### Layer 5 — AI Assistant + Orchestrator

- Calls OpenAI API (`OPENAI_MODEL` env var, default `gpt-4.1-mini`)
- Names cluster profiles based on job samples
- Orchestrates the full pipeline execution order
- Writes named profiles to `profiles` table

#### Layer 6 — Telegram Bot

- Subscription-gated chatbot with **Free / Plus ($9.99/mo) / Pro Plus ($19.99/mo)** plans
- Commands: `/start`, `/help`, `/cancel`; all navigation via inline keyboards
- Inline sections: What can this bot do?, Pricing, Chat with AI, Support, Privacy
- Personalised Pricing screen — shows upgrade button for Plus → Pro Plus users
- Support flow: message forwarded to admin, user picks Telegram / email / no reply
- Cancel subscription flow with Stripe period-end date fetched via API
- On `/start`: syncs user to `bot_users` table + Google Sheets CRM

#### Layer 7 — Stripe Webhook + Pay Redirects

- aiohttp HTTP server, listens on port `WEBHOOK_PORT` (default `8080`)
- `POST /webhook` — Stripe webhook endpoint (signature verified via `STRIPE_WEBHOOK_SECRET`)
  - `checkout.session.completed` → activates subscription in `subscriptions` table, notifies user
  - `customer.subscription.updated` → updates plan/status, notifies user
  - `customer.subscription.deleted` → marks cancelled, notifies user
- `GET /pay/plus?uid=<telegram_id>` → redirects to Stripe Plus payment link
- `GET /pay/pro-plus?uid=<telegram_id>` → redirects to Stripe Pro Plus payment link
  (shows clean `vacancy-mirror.com` domain in Telegram instead of raw Stripe URLs)
- All subscription changes synced to Google Sheets CRM

### Resources

```yaml
Image: Dockerfile.backend
Memory: 4 GB
CPU: 3.5 cores
Restart: unless-stopped
Ports:
  - 8080:8080  (Stripe webhook + pay redirects, public HTTPS via reverse proxy)
Network: hetzner-private (10.0.0.x)
Env:
  DB_URL: postgresql://app:${DB_PASSWORD}@localhost:5432/vacancy_mirror
  OPENAI_API_KEY: ${OPENAI_API_KEY}
  OPENAI_MODEL: gpt-4.1-mini
  TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
  SUPPORT_ADMIN_ID: ${SUPPORT_ADMIN_ID}
  STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}
  STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET}
  STRIPE_PLUS_URL: ${STRIPE_PLUS_URL}
  STRIPE_PRO_PLUS_URL: ${STRIPE_PRO_PLUS_URL}
  WEBHOOK_PORT: 8080
  WEBHOOK_BASE_URL: https://vacancy-mirror.com
  GOOGLE_SHEETS_ID: ${GOOGLE_SHEETS_ID}
  GOOGLE_SERVICE_ACCOUNT_JSON: ${GOOGLE_SERVICE_ACCOUNT_JSON}
  LOG_LEVEL: INFO
```

---

---

## 🖥️ HARDWARE REQUIREMENTS

### Minimum Configuration (CX22)

```
CPU:           2 vCPU (Intel/AMD)
RAM:           4 GB
Storage:       40 GB SSD
Network:       Unlimited bandwidth
Price:         ~€4/month
Status:        TIGHT - will work but may experience slowdowns during embeddings
```

### Recommended Configuration (CX32) ⭐

```
CPU:           4 vCPU (Intel/AMD)
RAM:           8 GB
Storage:       80 GB SSD
Network:       Unlimited bandwidth
Price:         ~€9/month
Status:        IDEAL - comfortable headroom for all operations
```

### High-Performance Configuration (CX42)

```
CPU:           8 vCPU (Intel/AMD)
RAM:           16 GB
Storage:       160 GB SSD
Network:       Unlimited bandwidth
Price:         ~€20/month
Status:        OVERKILL - for processing 5+ categories simultaneously
```

**RECOMMENDATION: CX32 (Best cost/performance ratio)**

---

## 📦 SOFTWARE STACK

### Operating System

```
OS:            Ubuntu 24.04 LTS (latest stable)
Kernel:        Linux 6.8+
Init System:   systemd
```

### Container Runtime

```
Docker:        27.0+ (latest stable)
Docker Compose: 2.25+
Registry:      Docker Hub (public images)
```

### Database

```
PostgreSQL:    16.2 (via pgvector image)
pgvector:      0.7.0 (vector extension)
Storage:       10-500 MB (grows ~50-100 MB/month)
Connection:    localhost:5432
```

### Python Environment

```
Python:        3.13.5 (in container)
Package Manager: pip 24.0+
Virtual Env:   NOT NEEDED (containerized)
```

---

## 📚 PYTHON DEPENDENCIES

### Core Data Processing

```
psycopg2-binary>=2.9          # PostgreSQL adapter
sentence-transformers>=3.0    # BAAI/bge-small-en-v1.5 model (384-dim)
scikit-learn>=1.3             # Clustering algorithms
numpy>=1.24                   # Numerical computations
```

### Telegram Bot

```
python-telegram-bot>=21.0     # PTB async bot framework
```

### Payments & CRM

```
aiohttp>=3.9                  # Stripe webhook HTTP server
gspread>=6.0                  # Google Sheets API client
```

### Browser Automation (Anti-Bot)

```
nodriver>=0.28                # Real Chrome browser control
asyncio (built-in)            # Async/await support
```

### LLM Integration

```
urllib (built-in)             # HTTP requests to OpenAI API
(no requests library - per architecture spec)
```

### Utilities

```
python-dotenv>=1.0            # Environment variable management
typing (built-in)             # Type hints
pathlib (built-in)            # Path handling
```

**Total dependencies:** ~10 main packages + their sub-dependencies  
**Download size:** ~400 MB (sentence-transformers bge-small model)

---

## 🐳 DOCKER CONTAINER ARCHITECTURE

### Service 1: PostgreSQL Database

```yaml
Service Name: postgres
Base Image: pgvector/pgvector:pg16
Memory Limit: 2GB
CPU Limit: 1.0
Restart Policy: unless-stopped
Health Check: pg_isready -U app every 10s
Volumes:
  - postgres-data:/var/lib/postgresql/data
  - ./infra/db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
Ports:
  - 5432:5432 (internal only, not exposed to public)
Environment: POSTGRES_DB=vacancy_mirror
  POSTGRES_USER=app
  POSTGRES_PASSWORD=${DB_PASSWORD}
```

### Service 2: Scraper/Pipeline

```yaml
Service Name: scraper
Build: From ./Dockerfile
Memory Limit: 4GB
CPU Limit: 3.5
Restart Policy: no (on-demand via cron)
Depends On: postgres (service_healthy)
Volumes:
  - /var/lib/scraper-data:/data (for raw JSON cache)
Ports: NONE (internal service)
Environment: DB_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/vacancy_mirror
  OPENAI_API_KEY=${OPENAI_API_KEY}
  OPENAI_MODEL=gpt-4.1-mini
  PROXY_URL=${PROXY_URL}
  LOG_LEVEL=INFO
Command: python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline
```

### Container Resource Budget

```
PostgreSQL:
  - RAM: 2 GB (shared buffer pool)
  - CPU: 1.0 core (mostly idle, spikes during queries)
  - Disk: RW 50-100 MB/s

Scraper:
  - RAM: 3-4 GB (model loading + browser memory)
  - CPU: 2.5-3.5 cores (during embeddings generation)
  - Disk: RW 100-200 MB/s (during scraping)
```

---

## 💾 DATA REQUIREMENTS

### Estimated Database Sizes

```
raw_jobs table:              ~2500 records × 50 KB  = ~125 MB
pattern_jobs table:          ~2500 records × 30 KB  = ~75 MB
pattern_normalized_jobs:     ~2500 records × 25 KB  = ~60 MB
job_embeddings:              ~2500 × 384 float32    = ~4 MB
job_clusters:                6-10 clusters, ~1 KB each = <1 MB
profiles:                    6-12 records × 5 KB    = <100 KB
scrape_runs:                 365 records × 1 KB     = <1 MB
subscriptions:               ~1000 users × 1 KB     = ~1 MB
bot_users:                   ~1000 users × 0.5 KB   = ~0.5 MB

TOTAL:                       ~270 MB (initial)
MONTHLY GROWTH:              ~50-100 MB (new jobs + snapshots)
6-MONTH PROJECTION:          ~600-800 MB
12-MONTH PROJECTION:         ~1.2-1.6 GB (still well under 80 GB)
```

### Backup Strategy

```
Full backup:    Weekly (Sunday 02:00 UTC) = ~50-100 MB compressed
Incremental:    Daily (every day 02:00 UTC)
Retention:      6 months of full backups
Storage:        /backups/ on SSD
```

### Cache/Temp Data

```
Downloaded models:     ~400 MB (BAAI/bge-small-en-v1.5)
Embeddings cache:      ~10-50 MB
Raw JSON cache:        ~100-200 MB
Total temp:            ~550 MB (pre-allocated)
```

---

## ⚡ PERFORMANCE CHARACTERISTICS

### Pipeline Execution Timeline

```
Step 1: Build Pattern Jobs
  - Operation: Parse raw JSON, regex extraction
  - Input: 2500 raw jobs (from DB)
  - Output: 2500 pattern jobs
  - Duration: ~5 minutes
  - Resources: 1 CPU, 512 MB RAM

Step 2: Normalize Pattern Jobs
  - Operation: Text cleaning, standardization
  - Input: 2500 pattern jobs
  - Output: 2500 normalized jobs
  - Duration: ~5 minutes
  - Resources: 1 CPU, 256 MB RAM

Step 3: Build Job Embeddings
  - Operation: sentence-transformers batch inference
  - Input: 2500 normalized job descriptions
  - Output: 2500 × 384-dim float32 vectors (bge-small-en-v1.5)
  - Duration: ~1-2 minutes (CPU)
  - Resources: 2 CPU, 1.5 GB RAM
  - Batch Size: 32 jobs per batch

Step 4: Cluster Job Embeddings
  - Operation: NearestNeighbors clustering
  - Input: 2500 embeddings, radius=0.06, cosine similarity
  - Output: 6-10 clusters
  - Duration: ~2 seconds
  - Resources: 1 CPU, 1 GB RAM

Step 5: Build Top Demanded Profiles
  - Operation: Database joins and aggregation
  - Input: clusters + raw jobs
  - Output: 6-12 profile records
  - Duration: ~1 minute
  - Resources: 1 CPU, 512 MB RAM

Step 6: Name Top Demanded Profiles
  - Operation: OpenAI API calls (LLM-based naming)
  - Input: 6-12 profile descriptions
  - Output: Named profiles
  - Duration: ~1-2 minutes
  - Resources: Network I/O (minimal CPU/RAM)
  - API Calls: 6-12 requests to gpt-4.1-mini
  - Estimated API Cost: $0.05-0.15 per run

Step 7: Build Semantic Core Profiles
  - Operation: JSON field generation
  - Input: profiles + sample job titles
  - Output: profiles with semantic_core JSON
  - Duration: ~1 minute
  - Resources: 1 CPU, 256 MB RAM

TOTAL PIPELINE DURATION: 3.5-4 hours (per run)
```

### Resource Utilization During Pipeline

```
During Idle (between runs):
  - CPU: 2-5% (PostgreSQL background tasks)
  - RAM: 1-1.5 GB (PostgreSQL + app base)
  - Disk I/O: 0%
  - Network: <1 Mbps

During Scraping (if enabled):
  - CPU: 40-60% (nodriver + parsing)
  - RAM: 2.5-3 GB (Chrome browser)
  - Disk I/O: 100-200 MB/s
  - Network: 5-50 Mbps

During Embeddings:
  - CPU: 80-100% (all cores busy)
  - RAM: 3.5-4 GB (model + batches)
  - Disk I/O: 50-100 MB/s (cache reads)
  - Network: <1 Mbps

Peak Load:
  - CPU: 100% (all 4 cores on CX32)
  - RAM: 4-5 GB peak (CX32 has 8GB, safe margin)
  - Disk: Heavy R/W
  - Network: 50+ Mbps
```

---

## 🌍 NETWORK REQUIREMENTS

### Upstream Services

```
Upwork.com:           TCP 443 (HTTPS)
                      RPS: 1-2 requests/second
                      Bandwidth: 2-5 Mbps
                      Latency tolerance: <5 seconds

api.openai.com:       TCP 443 (HTTPS)
                      RPS: 1 request/10 seconds
                      Bandwidth: <100 Kbps
                      Latency: <5 seconds

api.telegram.org:     TCP 443 (HTTPS)
                      Used for: Telegram Bot API (polling + webhook)
                      RPS: 1-5 requests/second

api.stripe.com:       TCP 443 (HTTPS)
                      Used for: Stripe payment API calls
                      Bandwidth: <100 Kbps

sheets.googleapis.com: TCP 443 (HTTPS)
                      Used for: Google Sheets CRM sync

Hugging Face Hub:     TCP 443 (HTTPS)
                      Used for: Model download (one-time)
                      Bandwidth: 50-100 Mbps (on first run)
                      Size: ~130 MB (bge-small-en-v1.5)
```

### Inbound

```
SSH:                  TCP 22 (for management)
                      Only from your IP (recommended)
Stripe Webhook:       TCP 8080 (HTTPS via reverse proxy, public)
                      Required: Stripe sends POST /webhook here
```

### Firewall Rules

```
Outbound:
  - HTTPS to Upwork.com: ALLOW
  - HTTPS to api.openai.com: ALLOW
  - HTTPS to api.telegram.org: ALLOW
  - HTTPS to api.stripe.com: ALLOW
  - HTTPS to sheets.googleapis.com: ALLOW
  - HTTPS to huggingface.co: ALLOW
  - DNS: ALLOW (UDP 53)

Inbound:
  - SSH: ALLOW from your IP only
  - TCP 80/443: ALLOW (reverse proxy / Let's Encrypt)
  - TCP 8080: ALLOW (Stripe webhook, via reverse proxy)
  - PostgreSQL 5432: BLOCK (no external access)
```

---

## 🔐 SECURITY CONFIGURATION

### Environment Variables (MUST BE SET)

```bash
# PostgreSQL (REQUIRED)
DB_PASSWORD=<strong_random_password_min_32_chars>

# OpenAI (REQUIRED for RAG pipeline)
OPENAI_API_KEY=sk-proj-<your_actual_key>
OPENAI_MODEL=gpt-4.1-mini

# Telegram Bot (REQUIRED)
TELEGRAM_BOT_TOKEN=<bot_token_from_botfather>
SUPPORT_ADMIN_ID=<your_telegram_user_id>

# Stripe Payments (REQUIRED)
STRIPE_SECRET_KEY=sk_live_<your_stripe_secret_key>
STRIPE_WEBHOOK_SECRET=whsec_<your_stripe_webhook_secret>
STRIPE_PLUS_URL=https://buy.stripe.com/<plus_payment_link>
STRIPE_PRO_PLUS_URL=https://buy.stripe.com/<pro_plus_payment_link>

# Webhook server (REQUIRED)
WEBHOOK_PORT=8080
WEBHOOK_BASE_URL=https://vacancy-mirror.com

# Google Sheets CRM (REQUIRED)
GOOGLE_SHEETS_ID=<spreadsheet_id_from_url>
GOOGLE_SERVICE_ACCOUNT_JSON=secrets/google_service_account.json

# Proxy (OPTIONAL, if using rotating proxy)
PROXY_URL_WEBDEV=http://proxy-ip:port
PROXY_USER=username
PROXY_PASS=password

# Logging
LOG_LEVEL=INFO
```

### File Permissions

```
/root/vacancy-mirror-chatbot-rag/.env      : 0600 (root only)
/var/lib/scraper-data/                     : 0755 (docker user)
/backups/                                  : 0700 (root only)
```

### Database Security

```
- PostgreSQL runs on localhost only (no external access)
- Non-root database user: app (with limited privileges)
- No default passwords (random generated on container start)
- Backups encrypted if stored in cloud
```

### API Key Management

```
- OpenAI key stored in .env (NOT in code)
- .env file in .gitignore
- Rotate keys every 90 days
- Monitor API usage for unauthorized calls
```

---

## 📅 CRON SCHEDULE CONFIGURATION

### Daily Full Pipeline

```bash
# Run at midnight UTC every day
0 0 * * * cd /root/vacancy-mirror-chatbot-rag && \
  docker-compose exec -T scraper \
  python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline \
  >> /var/log/scraper.log 2>&1

# Email notification on failure (optional)
0 0 * * * ... || mail -s "Scraper failed" admin@example.com
```

### Database Backup

```bash
# Full backup every Sunday at 02:00 UTC
0 2 * * 0 docker-compose -f /root/vacancy-mirror-chatbot-rag/docker-compose.yml \
  exec -T postgres \
  pg_dump -U app vacancy_mirror | \
  gzip > /backups/vacancy_mirror_full_$(date +\%Y\%m\%d).sql.gz

# Incremental backup every weekday at 02:00 UTC
0 2 * * 1-5 docker-compose -f /root/vacancy-mirror-chatbot-rag/docker-compose.yml \
  exec -T postgres \
  pg_dump -U app vacancy_mirror | \
  gzip > /backups/vacancy_mirror_inc_$(date +\%Y\%m\%d_%H%M%S).sql.gz
```

### Cleanup Old Backups

```bash
# Delete backups older than 6 months, every Sunday at 03:00 UTC
0 3 * * 0 find /backups -name "*.sql.gz" -mtime +180 -delete
```

### System Health Check

```bash
# Check disk usage, every 6 hours
0 */6 * * * df -h /dev/sda1 | tail -1 | \
  awk '{if ($5+0 > 80) print "DISK ALERT: "$5}' | \
  mail -s "Server Alert" admin@example.com
```

---

## 📊 MONITORING & LOGGING

### Log Locations

```
Docker logs:           docker logs -f <container_name>
Scraper pipeline:      /var/log/scraper.log
PostgreSQL:            docker logs postgres
System journal:        journalctl -u docker
```

### Key Metrics to Monitor

```
Pipeline Status:
  - ✓ Completed successfully
  - ✗ Failed with error
  - ⏱ Took X hours to complete

Database Size:
  - SELECT pg_database_size('vacancy_mirror') / 1024 / 1024 AS size_mb;

Cluster Count:
  - SELECT COUNT(*) FROM job_clusters;

Profile Count:
  - SELECT COUNT(*) FROM profiles;

Last Run:
  - SELECT MAX(finished_at) FROM scrape_runs WHERE status='done';
```

### Alert Conditions

```
- Pipeline fails (exit code != 0)
- Database connection lost
- Disk space <5 GB free
- Memory usage >7 GB on CX32
- OpenAI API key invalid (401 errors)
- Database size >70 GB
```

---

## 🚀 DEPLOYMENT CHECKLIST

Before going live, ensure:

- [ ] CX32 or larger server provisioned
- [ ] Ubuntu 24.04 LTS installed and updated
- [ ] SSH key-based access configured
- [ ] Docker 27.0+ installed and working
- [ ] Docker Compose 2.25+ installed
- [ ] .env file created with all required variables:
  - [ ] DB_PASSWORD (strong, 32+ chars)
  - [ ] OPENAI_API_KEY (valid OpenAI key)
  - [ ] OPENAI_MODEL=gpt-4.1-mini
  - [ ] TELEGRAM_BOT_TOKEN (from BotFather)
  - [ ] SUPPORT_ADMIN_ID (admin Telegram user ID)
  - [ ] STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
  - [ ] STRIPE_PLUS_URL, STRIPE_PRO_PLUS_URL
  - [ ] WEBHOOK_PORT=8080, WEBHOOK_BASE_URL
  - [ ] GOOGLE_SHEETS_ID
  - [ ] GOOGLE_SERVICE_ACCOUNT_JSON path
  - [ ] PROXY_URL (if needed)
- [ ] Google service account JSON placed in secrets/ (gitignored)
- [ ] Service account shared as Editor on Google Sheets spreadsheet
- [ ] Stripe account configured:
  - [ ] Webhook endpoint registered at https://vacancy-mirror.com/webhook
  - [ ] Payment links created for Plus and Pro Plus plans
  - [ ] STRIPE_WEBHOOK_SECRET from Stripe dashboard
- [ ] Port 8080 open in firewall (for Stripe webhook inbound)
- [ ] Project cloned to /root/vacancy-mirror-chatbot-rag
- [ ] docker-compose up -d executes without errors
- [ ] PostgreSQL health check passes
- [ ] Initial import-raw-to-db completes successfully
- [ ] Full pipeline run-full-pipeline completes successfully
- [ ] stripe-webhook service starts without errors
- [ ] telegram-bot service starts without errors
- [ ] Cron jobs configured in /etc/crontab
- [ ] Backup directory created: mkdir -p /backups
- [ ] Firewall rules applied (SSH + 8080 inbound, HTTPS outbound)
- [ ] Monitoring/alerting configured
- [ ] Documentation updated with server IP

---

## 💰 ESTIMATED COSTS

### Monthly Hetzner

```
CX32 Server:        €9
Backup Storage:     €0 (included)
Network:            €0 (unlimited)
TOTAL:              €9/month
```

### Monthly OpenAI (RAG pipeline Step 6)

```
gpt-4.1-mini calls: ~30 per month × 6-12 profiles
Input tokens:       ~500 per call = 180,000 tokens/month
Output tokens:      ~100 per call = 36,000 tokens/month
Estimated cost:     ~$0.10-0.20/month (gpt-4.1-mini is cheaper than gpt-4-mini)
```

### Stripe Payments

```
Platform fee:       $0/month (no monthly Stripe fee)
Per-transaction:    2.9% + $0.30 per successful payment
Example (10 subs):  ~$3.20/month on $100 revenue
```

### Google Sheets

```
Google Sheets API:  Free (up to 300 requests/minute)
Service account:    Free (Google Cloud free tier)
TOTAL:              $0/month
```

### TOTAL MONTHLY COST

```
Hetzner:            €9.00 (~$10 USD)
OpenAI:             ~$0.20 (minimal)
Stripe:             % of revenue (no fixed cost)
Google:             $0.00
TOTAL:              ~$10.20/month + Stripe transaction fees
```

---

## 📞 SUPPORT & TROUBLESHOOTING

### Common Issues

**Issue: "Out of memory" during embeddings**

- Solution: Reduce batch_size in cli.py (change from 32 to 16)
- Alternative: Upgrade to CX42 (16 GB RAM)

**Issue: "Connection refused" to PostgreSQL**

- Solution: Verify postgres container is running: `docker-compose ps`
- Check health: `docker-compose exec postgres pg_isready -U app`

**Issue: "OpenAI API error: 401"**

- Solution: Verify OPENAI_API_KEY is valid and not expired
- Check: `echo $OPENAI_API_KEY` (must not be empty)

**Issue: "Disk space full"**

- Solution: Delete old backups: `rm /backups/*.sql.gz`
- Monitor: `df -h /` (keep >10 GB free)

**Issue: Pipeline takes >5 hours**

- Solution: May be normal on CX22 with heavy load
- Check: `docker stats` for CPU/RAM bottlenecks
- Upgrade: Consider CX32 if consistent slowness

**Issue: Stripe webhook returns 400 / signature verification failed**

- Solution: Verify STRIPE_WEBHOOK_SECRET matches the one in the Stripe dashboard
- Check: The webhook endpoint in Stripe must point to `https://vacancy-mirror.com/webhook`
- Tip: Use `stripe listen --forward-to localhost:8080/webhook` for local testing

**Issue: Stripe webhook events not received**

- Solution: Ensure port 8080 is open in the Hetzner firewall
- Check: `curl -I https://vacancy-mirror.com/webhook` must return 405 (POST only)
- Verify the stripe-webhook process is running: `ps aux | grep backend.cli`

**Issue: Google Sheets sync fails with 403**

- Solution: Ensure the service account email is shared as Editor on the spreadsheet
- Check: Service account JSON path matches GOOGLE_SERVICE_ACCOUNT_JSON env var
- Verify: `secrets/google_service_account.json` exists and is valid JSON

**Issue: Telegram bot conflict error (409)**

- Cause: Multiple bot instances running simultaneously
- Solution: `pkill -9 -f "backend.cli"`, wait 5 seconds, then restart
- Prevention: Never start the bot twice; use a process manager (systemd/supervisor)

**Issue: Bot not responding to users**

- Check: `tail -f /var/log/bot.log` for error messages
- Verify: `echo $TELEGRAM_BOT_TOKEN` is correct
- Check: Bot process is running: `ps aux | grep telegram-bot`

---

## 📚 USEFUL COMMANDS

```bash
# ── Docker / Pipeline ──────────────────────────────────────────

# View active containers
docker-compose ps

# View logs
docker-compose logs -f scraper
docker-compose logs -f postgres

# Run manual pipeline
docker-compose exec scraper \
  python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline

# Check database size
docker-compose exec postgres psql -U app -d vacancy_mirror \
  -c "SELECT pg_size_pretty(pg_database_size('vacancy_mirror'));"

# Create manual backup
docker-compose exec postgres pg_dump -U app vacancy_mirror | \
  gzip > /backups/manual_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore from backup
gunzip < /backups/vacancy_mirror_20260327.sql.gz | \
  docker-compose exec -T postgres psql -U app -d vacancy_mirror

# Stop all services
docker-compose down

# Restart services
docker-compose restart

# Rebuild and redeploy
docker-compose down
docker-compose up -d --build


# ── Telegram Bot & Stripe Webhook ─────────────────────────────

# Start Stripe webhook server (production)
STRIPE_WEBHOOK_SECRET="whsec_..." \
  .venv/bin/python -m backend.cli stripe-webhook \
  >> /var/log/webhook.log 2>&1 &

# Start Telegram bot (production)
.venv/bin/python -m backend.cli telegram-bot \
  >> /var/log/bot.log 2>&1 &

# Check running bot/webhook processes
ps aux | grep backend.cli

# Stop all bot/webhook processes
pkill -9 -f "backend.cli"

# Tail bot logs
tail -f /var/log/bot.log
tail -f /var/log/webhook.log

# Check subscriptions in DB
docker-compose exec postgres psql -U app -d vacancy_mirror \
  -c "SELECT * FROM subscriptions ORDER BY created_at DESC LIMIT 20;"

# Check bot users in DB
docker-compose exec postgres psql -U app -d vacancy_mirror \
  -c "SELECT * FROM bot_users ORDER BY created_at DESC LIMIT 20;"
```

---

## 📝 VERSION HISTORY

| Version | Date       | Changes                                                                          |
| ------- | ---------- | -------------------------------------------------------------------------------- |
| 1.0     | 2026-03-27 | Initial specification for CX32 server                                            |
| 2.0     | 2026-03-29 | Two-container architecture, 7-layer backend, L1–L4                               |
| 3.0     | 2026-03-29 | Stripe payments, Google Sheets CRM, Telegram subscription plans, bge-small model |

---

**Last Updated:** 29 March 2026  
**Author:** GitHub Copilot  
**Status:** CURRENT
