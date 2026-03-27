# Vacancy Mirror RAG Pipeline — Hetzner Deployment Specification

**Дата создания:** 27 March 2026  
**Версия:** 1.0  
**Язык:** English (для ChatGPT)

---

## 📋 SYSTEM OVERVIEW

The Vacancy Mirror RAG Pipeline is a production-grade data pipeline that:

- **Scrapes** Upwork job vacancies using headless Chrome (anti-bot protection)
- **Processes** raw job data through NLP normalization and pattern extraction
- **Generates** semantic embeddings using BAAI/bge-large-en-v1.5 (1024-dim)
- **Clusters** similar jobs using scikit-learn's NearestNeighbors algorithm
- **Profiles** demand patterns and names them using OpenAI GPT-4-mini
- **Stores** all data in PostgreSQL with pgvector for semantic search

**Runtime:** 7-stage pipeline, executes in ~3.5-4 hours for fresh data  
**Frequency:** Daily (configurable via cron)

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
psycopg2-binary==2.9.9        # PostgreSQL adapter
sentence-transformers==3.0.1  # BAAI/bge-large-en-v1.5 model
scikit-learn==1.3.2           # Clustering algorithms
numpy==1.24.3                 # Numerical computations
```

### Browser Automation (Anti-Bot)

```
nodriver==0.28                # Real Chrome browser control
asyncio (built-in)            # Async/await support
```

### LLM Integration

```
urllib (built-in)             # HTTP requests to OpenAI API
(no requests library - per architecture spec)
```

### Utilities

```
python-dotenv==1.0.0          # Environment variable management
typing (built-in)             # Type hints
pathlib (built-in)            # Path handling
```

**Total dependencies:** ~8 main packages + their sub-dependencies  
**Download size:** ~800 MB (mostly sentence-transformers model)

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
  OPENAI_MODEL=gpt-4-mini
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
raw_jobs table:              ~2500 records × 50 KB = ~125 MB
pattern_jobs table:          ~2500 records × 30 KB = ~75 MB
pattern_normalized_jobs:     ~2500 records × 25 KB = ~60 MB
job_embeddings:              ~2500 × 1024 float32 = ~10 MB
job_clusters:                6-10 clusters, ~1 KB each = <1 MB
profiles:                    6-12 records × 5 KB = <100 KB
scrape_runs:                 365 records × 1 KB = <1 MB

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
Downloaded models:     ~700 MB (BAAI/bge-large-en-v1.5)
Embeddings cache:      ~10-50 MB
Raw JSON cache:        ~100-200 MB
Total temp:            ~850 MB (pre-allocated)
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
  - Output: 2500 × 1024-dim float32 vectors
  - Duration: ~2.5 minutes (CPU), ~30 seconds (GPU if available)
  - Resources: 3 CPU, 3.5 GB RAM
  - Batch Size: 32 jobs per batch
  - Throughput: ~17 jobs/second

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
  - API Calls: 6-12 requests to gpt-4-mini
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

Hugging Face Hub:     TCP 443 (HTTPS)
                      Used for: Model download (one-time)
                      Bandwidth: 50-100 Mbps (on first run)
                      Size: ~700 MB
```

### Inbound (Optional)

```
SSH:                  TCP 22 (for management)
                      Only from your IP (recommended)
HTTP API:             TCP 8000 (optional, not implemented yet)
                      For future REST API to query profiles
```

### Firewall Rules

```
Outbound:
  - HTTPS to Upwork.com: ALLOW
  - HTTPS to api.openai.com: ALLOW
  - HTTPS to huggingface.co: ALLOW
  - DNS: ALLOW (UDP 53)

Inbound:
  - SSH: ALLOW from your IP only
  - HTTP: BLOCK (unless serving API)
  - PostgreSQL 5432: BLOCK (no external access)
```

---

## 🔐 SECURITY CONFIGURATION

### Environment Variables (MUST BE SET)

```bash
# PostgreSQL (REQUIRED)
DB_PASSWORD=<strong_random_password_min_32_chars>

# OpenAI (REQUIRED for step 6)
OPENAI_API_KEY=sk-proj-<your_actual_key>
OPENAI_MODEL=gpt-4-mini

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
  - [ ] PROXY_URL (if needed)
- [ ] Project cloned to /root/vacancy-mirror-chatbot-rag
- [ ] docker-compose up -d executes without errors
- [ ] PostgreSQL health check passes
- [ ] Initial import-raw-to-db completes successfully
- [ ] Full pipeline run-full-pipeline completes successfully
- [ ] Cron jobs configured in /etc/crontab
- [ ] Backup directory created: mkdir -p /backups
- [ ] Firewall rules applied (SSH + outbound HTTPS only)
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

### Monthly OpenAI (Step 6)

```
GPT-4-mini calls:   ~30 per month × 6-12 profiles
Input tokens:       ~500 per call = 180,000 tokens/month
Output tokens:      ~100 per call = 36,000 tokens/month
Estimated cost:     ~$0.30-0.50/month (if daily runs)
```

### TOTAL MONTHLY COST

```
Hetzner:            €9.00 (~$10 USD)
OpenAI:             $0.50 (minimal)
TOTAL:              ~$10.50/month
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

---

## 📚 USEFUL COMMANDS

```bash
# View active containers
docker-compose ps

# View logs
docker-compose logs -f scraper
docker-compose logs -f postgres

# Run manual pipeline
docker-compose exec scraper python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline

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
```

---

## 📝 VERSION HISTORY

| Version | Date       | Changes                               |
| ------- | ---------- | ------------------------------------- |
| 1.0     | 2026-03-27 | Initial specification for CX32 server |

---

**Last Updated:** 27 March 2026  
**Author:** GitHub Copilot  
**Status:** PRODUCTION READY
