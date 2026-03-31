# Vacancy Mirror — Freelance Market Intelligence Bot**AI-powered Telegram bot that delivers freelance market insights to Upwork freelancers.**Scrapes public job listings from Upwork, processes them through a 7-step RAG pipeline, and serves personalized market intelligence via a subscription-based Telegram chatbot. Includes automated scraping with Cloudflare bypass, embeddings-based clustering, OpenAI-powered profile naming, and Stripe payment integration.---## 📋 Table of Contents- [Architecture Overview](#architecture-overview)- [System Components](#system-components)- [Tech Stack](#tech-stack)- [Infrastructure](#infrastructure)- [Getting Started](#getting-started)- [Scraper Service](#scraper-service)- [RAG Pipeline](#rag-pipeline)- [Telegram Bot](#telegram-bot)- [Payment & User Management](#payment--user-management)- [Deployment](#deployment)- [Configuration](#configuration)- [Development](#development)- [Troubleshooting](#troubleshooting)- [Performance & Scaling](#performance--scaling)---## 🏗️ Architecture Overview`┌─────────────────────────────────────────────────────────────────┐│                    UPWORK SEARCH PAGES (SSR HTML)               │└───────────────────────────────┬─────────────────────────────────┘                                │                                ▼┌─────────────────────────────────────────────────────────────────┐│              SCRAPER SERVICE (Hetzner CPX11 × N)                ││  • nodriver + Chromium (headless)                               ││  • FlareSolverr (Cloudflare bypass)                             ││  • Unique IP per server (anti-bot)                              ││  • 72 sec/page, ~250 jobs/run                                   │└───────────────────────────────┬─────────────────────────────────┘                                │                                ▼┌─────────────────────────────────────────────────────────────────┐│                  POSTGRESQL (raw_jobs table)                    ││  • Job listings with full metadata                              ││  • Deduplication by job UID                                     ││  • Scrape run tracking                                          │└───────────────────────────────┬─────────────────────────────────┘                                │                                ▼┌─────────────────────────────────────────────────────────────────┐│            7-STEP RAG PIPELINE (Backend, CPX32)                 ││  1. build-pattern-jobs          ← Extract skills, deduplicate   ││  2. normalize-pattern-jobs      ← Standardize formats          ││  3. build-job-embeddings        ← BAAI/bge-small-en-v1.5       ││  4. cluster-job-embeddings      ← NearestNeighbors, cosine     ││  5. build-top-demanded-profiles ← Cluster analysis             ││  6. name-top-demanded-profiles  ← OpenAI GPT naming            ││  7. build-semantic-core-profiles← Semantic search index        │└───────────────────────────────┬─────────────────────────────────┘                                │                                ▼┌─────────────────────────────────────────────────────────────────┐│              POSTGRESQL + pgvector Extension                    ││  • Vector embeddings (384-dim)                                  ││  • Semantic search capabilities                                 ││  • Profile clusters & metadata                                  │└───────────────────────────────┬─────────────────────────────────┘                                │                                ▼┌─────────────────────────────────────────────────────────────────┐│          TELEGRAM BOT (Subscription-Gated RAG Chatbot)          ││  • Free / Plus / Pro Plus plans                                 ││  • Rate-limited AI conversations                                ││  • Stripe payment integration                                   ││  • Google Sheets user CRM                                       ││  • Support messaging system                                     │└─────────────────────────────────────────────────────────────────┘`---## 🔧 System Components### 1. Scraper Service**Purpose:** Collects job listings from Upwork without detection or blocking.**Key Features:**- **FlareSolverr Integration** — Automated Cloudflare bypass (no manual intervention)- **Residential Proxies** — Webshare rotating proxies with sticky sessions- **Checkpoint System** — Resume after crashes, save progress per page- **Rate Limiting** — Random delays (10-45 sec) between requests- **Duplicate Detection** — Skip jobs already in database- **Multi-Server Support** — Deploy on multiple servers with unique IPs**Technology:**- `nodriver` — Undetected Chrome automation- `FlareSolverr` — Cloudflare bypass service (v3.4.6, Chromium 142)- `PostgreSQL` — Job storage with metadata tracking**Performance:**- ~72 seconds per page (FlareSolverr: 23s, JS exec: 35-46s, delay: 34-44s)- ~250 jobs per 5-page run (~6 minutes)- Can scrape up to 5,000 jobs per category (100 pages × 50 jobs)### 2. RAG Pipeline**Purpose:** Processes raw job listings into actionable market intelligence.**Pipeline Steps:**1. **build-pattern-jobs** — Extract structured data from raw jobs2. **normalize-pattern-jobs** — Standardize data formats3. **build-job-embeddings** — Generate vector embeddings (BAAI/bge-small-en-v1.5, 384-dim)4. **cluster-job-embeddings** — Group similar jobs (NearestNeighbors, cosine similarity)5. **build-top-demanded-profiles** — Analyze demand patterns6. **name-top-demanded-profiles** — Generate human-readable names (OpenAI API)7. **build-semantic-core-profiles** — Build semantic search index**Technology:**- `sentence-transformers` — Embedding generation- `scikit-learn` — Clustering algorithms- `OpenAI API` — Profile naming- `pgvector` — Vector storage & search### 3. Telegram Bot**Purpose:** User-facing chatbot for market intelligence queries.**Features:**- **Free Plan** — 5 messages/day, basic market insights- **Plus Plan** ($9.99/month) — 100 messages/day, advanced analytics- **Pro Plus Plan** ($19.99/month) — Unlimited messages, priority support- AI-powered conversations with rate limiting- Subscription management via Stripe- Support messaging to admin- Privacy policy & terms of service**Technology:**- `aiogram` — Async Telegram Bot framework- `OpenAI API` — Chat completions- `Stripe API` — Payment processing- `Google Sheets API` — User CRM---## 💻 Tech Stack### Backend Services- **Python 3.13** — Core runtime- **PostgreSQL 15 + pgvector** — Database with vector search- **Docker & Docker Compose** — Containerization### Scraping & Automation- **nodriver** — Undetected Chrome automation- **FlareSolverr** — Cloudflare bypass service- **Chromium 142** — Browser engine### AI & ML- **sentence-transformers** — Embedding generation- **BAAI/bge-small-en-v1.5** — 384-dim embedding model- **OpenAI API** — GPT-based naming & chat- **scikit-learn** — Clustering algorithms- **pgvector** — Vector similarity search### Bot & API- **aiogram** — Telegram Bot framework- **Stripe API** — Payment processing- **Google Sheets API** — User management### Infrastructure- **Hetzner Cloud** — VPS hosting- **Vercel** — Frontend hosting (Next.js)---## 🌐 Infrastructure### Production Servers#### Backend Server (CPX32)- **Instance:** Hetzner CPX32 (8 vCPU, 16 GB RAM, 240 GB SSD)- **IP:** 178.104.110.28- **Services:** - PostgreSQL database - Telegram Bot - Stripe webhook - RAG pipeline workers - FlareSolverr (port 8191)#### Scraper Server (CPX11 × N)- **Instance:** Hetzner CPX11 (2 vCPU, 2 GB RAM, 40 GB SSD)- **Services:** - Scraper container - FlareSolverr container - Cron scheduler**Scaling:** Deploy multiple CPX11 instances with unique IPs to parallelize scraping.### External Services- **Webshare Proxies** — Residential proxies with sticky sessions- **Vercel** — Next.js frontend hosting- **GitHub Container Registry** — Docker image storage---## 🚀 Getting Started### Prerequisites- Docker & Docker Compose- Python 3.13+- PostgreSQL 15+- Node.js 18+ (for frontend)### Environment VariablesCreate `.env` file:`bash# DatabaseDATABASE_URL=postgresql://user:pass@localhost:5432/vacancy_mirror# Telegram BotTELEGRAM_BOT_TOKEN=your_bot_tokenADMIN_TELEGRAM_ID=your_telegram_id# OpenAI APIOPENAI_API_KEY=sk-...OPENAI_MODEL=gpt-4o-mini# StripeSTRIPE_SECRET_KEY=sk_test_...STRIPE_WEBHOOK_SECRET=whsec_...STRIPE_PRICE_ID_PLUS=price_...STRIPE_PRICE_ID_PRO_PLUS=price_...# Google SheetsGOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.jsonGOOGLE_SHEET_ID=your_spreadsheet_id# ScraperFLARESOLVERR_URL=http://flaresolverr:8191/v1PROXY_URL=http://user-session-ID:pass@p.webshare.io:80CHROME_PATH=/usr/bin/chromium`### Quick Start`bash# Clone repositorygit clone https://github.com/yourusername/vacancy-mirror-chatbot-rag.gitcd vacancy-mirror-chatbot-rag# Start servicesdocker compose up -d# Initialize databasepsql $DATABASE_URL < infra/db/init.sql# Run scraper (1 category, 5 pages)docker compose run --rm scraper python -m scraper.cli scrape \  --uid 531770282580668418 \  --label "Web, Mobile & Software Dev" \  --max-pages 5# Run RAG pipelinedocker compose exec backend python -m backend.cli rag pipeline# Start Telegram botdocker compose exec backend python -m backend.cli telegram-bot# Start Stripe webhookdocker compose exec backend python -m backend.cli stripe-webhook`---## 🕷️ Scraper Service### FlareSolverr IntegrationAutomated Cloudflare bypass without manual intervention.#### How It Works1. **FlareSolverr Request** — Scraper calls FlareSolverr API with target URL2. **Cloudflare Bypass** — FlareSolverr uses real Chromium to solve challenges3. **HTML Return** — Returns full HTML (~1.5MB) + 26 cookies + user agent4. **Browser Load** — Load HTML into nodriver via `document.write()`5. **JS Execution** — Browser executes JavaScript to build `window.__NUXT__`6. **Data Extraction** — Extract job listings from `__NUXT__.state.jobsSearch.jobs`#### Performance- **FlareSolverr fetch:** 23-24 seconds- **Browser JS execution:** 34-46 seconds- **Random delay:** 34-44 seconds- **Total per page:** ~72 seconds#### Configuration`yamlflaresolverr:  image: ghcr.io/flaresolverr/flaresolverr:latest  ports:    - "8191:8191"  environment:    LOG_LEVEL: info    CAPTCHA_SOLVER: nonescraper:  depends_on:    - flaresolverr  environment:    FLARESOLVERR_URL: http://flaresolverr:8191/v1`### Checkpoint SystemSaves progress after every page to survive crashes.**Features:**- Per-page checkpoints in `data/checkpoints/{category_uid}/page_{num}.json`- State tracking in `data/state_{category_uid}.json`- Automatic resume from last saved page- Graceful degradation on errors**Example:**`bash# First run (interrupted after page 2)docker compose run --rm scraper python -m scraper.cli scrape \  --uid 531770282580668418 --max-pages 5# Checkpoints saved, resume automatically continues from page 3docker compose run --rm scraper python -m scraper.cli scrape \  --uid 531770282580668418 --max-pages 5`### Proxy Configuration- **FlareSolverr:** Direct connection (no proxy) - Webshare proxy returns 0 cookies with FlareSolverr - Solution: Use direct connection for Cloudflare bypass- **nodriver Browser:** Uses Webshare residential proxy - Subsequent requests go through proxy - Hides scraper IP from rate limiting### Commands`bash# Scrape single categorydocker compose run --rm scraper python -m scraper.cli scrape \  --uid {CATEGORY_UID} \  --label "{CATEGORY_NAME}" \  --max-pages {NUM_PAGES}# Scrape all categoriesdocker compose run --rm scraper python -m scraper.cli scrape-all \  --max-pages-per-category 50# Show category load levelsdocker compose run --rm scraper python -m scraper.cli show-category-load`### Deployment`bash# Build & push imagedocker buildx build --platform linux/amd64 \  -t ghcr.io/martinlilt/vacancy-mirror-scraper:latest \  --push ./scraper# Deploy to serverssh root@178.104.110.28 "cd /etc/vacancy-mirror && \  docker compose pull scraper && \  docker compose up -d flaresolverr"# Run scraperssh root@178.104.110.28 "cd /etc/vacancy-mirror && \  docker compose run --rm scraper python -m scraper.cli scrape \    --uid 531770282580668418 --label 'Web Dev' --max-pages 50"`### Cron Scheduling`bash# Daily scraping at 3 AM0 3 * * * cd /etc/vacancy-mirror && docker compose run --rm scraper python -m scraper.cli scrape-all --max-pages-per-category 50 >> /var/log/scraper.log 2>&1`---## 🧠 RAG Pipeline### Pipeline Steps#### 1. build-pattern-jobsExtract structured data from raw HTML.`bashdocker compose exec backend python -m backend.cli rag build-pattern-jobs`#### 2. normalize-pattern-jobsStandardize data formats.`bashdocker compose exec backend python -m backend.cli rag normalize-pattern-jobs`#### 3. build-job-embeddingsGenerate 384-dim vector embeddings using `BAAI/bge-small-en-v1.5`.`bashdocker compose exec backend python -m backend.cli rag build-job-embeddings`**Technical:**- Batch size: 32 jobs- Processing time: ~0.5s per job- Similarity metric: Cosine similarity#### 4. cluster-job-embeddingsGroup similar jobs using NearestNeighbors.`bashdocker compose exec backend python -m backend.cli rag cluster-job-embeddings`#### 5. build-top-demanded-profilesAnalyze demand patterns from clusters.`bashdocker compose exec backend python -m backend.cli rag build-top-demanded-profiles`#### 6. name-top-demanded-profilesGenerate human-readable names using OpenAI.`bashdocker compose exec backend python -m backend.cli rag name-top-demanded-profiles`**Example output:** "Full-Stack React & Node.js Developer"**Cost:** ~$0.01 per 100 profiles (gpt-4o-mini)#### 7. build-semantic-core-profilesBuild semantic search index for chatbot.`bashdocker compose exec backend python -m backend.cli rag build-semantic-core-profiles`### Running Full Pipeline`bash# All steps sequentiallydocker compose exec backend python -m backend.cli rag pipeline`### Performance- **Total time:** 15-30 minutes for 10,000 jobs- **Embedding generation:** ~0.5s per job- **Clustering:** ~5 minutes for 10,000 jobs- **Profile naming:** ~1 minute for 100 profiles---## 💬 Telegram Bot### Subscription Plans| Feature | Free | Plus ($9.99/mo) | Pro Plus ($19.99/mo) ||---------|------|-----------------|----------------------|| Messages/day | 5 | 100 | Unlimited || Market insights | Basic | Advanced | Advanced || Profile recommendations | ✓ | ✓ | ✓ || Budget analysis | ✗ | ✓ | ✓ || Trend predictions | ✗ | ✗ | ✓ || Priority support | ✗ | ✗ | ✓ |### Commands- `/start` — Welcome screen with navigation- `/help` — Show available commands- `/status` — Check subscription & usage- `/cancel` — Cancel subscription### Inline Keyboard Navigation- 🤖 **What can this bot do?** — Feature breakdown- 💎 **Pricing** — Subscription plans- 💬 **Chat with AI** — Market intelligence- 🆘 **Support** — Contact admin- 📜 **Privacy Policy** — Legal text- 📄 **Terms of Service** — Usage terms### AI Chat Example```User: What are top skills for React developers?Bot: Based on recent market analysis:Top Skills for Full-Stack Developers:• React.js (78% of jobs)• Node.js (65% of jobs)• PostgreSQL/MongoDB (52% of jobs)• TypeScript (48% of jobs)• AWS/Docker (35% of jobs)Average Budget: $50-80/hourDemand Trend: ↑ 15% this monthMessages remaining: 4/5 (Free plan)

````

### Stripe Integration

1. User clicks upgrade in bot
2. Bot generates Stripe Checkout session
3. User completes payment
4. Webhook fires `checkout.session.completed`
5. Backend updates subscription status
6. Bot confirms and grants access

### Deployment

```bash
# Start bot
docker compose exec -d backend python -m backend.cli telegram-bot

# Start webhook
docker compose exec -d backend python -m backend.cli stripe-webhook

# Check logs
docker compose logs -f backend
````

---

## 💳 Payment & User Management

### Stripe Setup

#### Create Products

```bash
stripe products create \
  --name "Vacancy Mirror Plus" \
  --description "Advanced market insights"

stripe prices create \
  --product prod_... \
  --unit-amount 999 \
  --currency usd \
  --recurring interval=month
```

#### Configure Webhook

```bash
stripe webhook_endpoints create \
  --url https://your-domain.com/webhook/stripe \
  --enabled-events checkout.session.completed \
  --enabled-events invoice.paid \
  --enabled-events customer.subscription.deleted
```

#### Test Payments

Card: `4242 4242 4242 4242`  
Expiry: Any future date  
CVC: Any 3 digits

### Google Sheets Setup

1. Create service account in Google Cloud Console
2. Download JSON key file → `secrets/google_service_account.json`
3. Share spreadsheet with service account email
4. Configure environment variables

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
export GOOGLE_SHEET_ID=your_spreadsheet_id
```

---

## 🚀 Deployment

### Backend (CPX32)

```bash
# SSH to server
ssh root@178.104.110.28

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone & configure
cd /etc
git clone https://github.com/yourusername/vacancy-mirror-chatbot-rag.git vacancy-mirror
cd vacancy-mirror
nano .env  # Add environment variables

# Initialize database
docker compose up -d postgres
sleep 10
docker compose exec postgres psql -U vacancy_mirror -f /docker-entrypoint-initdb.d/init.sql

# Start services
docker compose up -d
docker compose ps
```

### Scraper (CPX11)

```bash
# Build & push
docker buildx build --platform linux/amd64 \
  -t ghcr.io/martinlilt/vacancy-mirror-scraper:latest \
  --push ./scraper

# Deploy
ssh root@scraper-ip "cd /etc/vacancy-mirror && \
  docker compose pull scraper && \
  docker compose up -d flaresolverr"

# Configure cron
crontab -e
# Add: 0 3 * * * cd /etc/vacancy-mirror && docker compose run --rm scraper python -m scraper.cli scrape-all --max-pages 50
```

### Frontend (Vercel)

```bash
npm install -g vercel
cd web/frontend
vercel --prod
```

---

## ⚙️ Configuration

### Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
TELEGRAM_BOT_TOKEN=123:ABC...
ADMIN_TELEGRAM_ID=123456789
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/json
GOOGLE_SHEET_ID=spreadsheet_id
FLARESOLVERR_URL=http://flaresolverr:8191/v1
PROXY_URL=http://user:pass@proxy:80
CHROME_PATH=/usr/bin/chromium
```

---

## 🛠️ Development

### Local Setup

```bash
git clone https://github.com/yourusername/vacancy-mirror-chatbot-rag.git
cd vacancy-mirror-chatbot-rag

python3 -m venv venv
source venv/bin/activate
pip install -e ./backend
pip install -e ./scraper

docker compose up -d postgres
psql $DATABASE_URL < infra/db/init.sql

# Run services
python -m backend.cli telegram-bot
python -m scraper.cli scrape --uid ... --max-pages 1
```

### Testing

```bash
cd backend && pytest
cd scraper && pytest
cd web/frontend && npm test
```

### Code Style

```bash
flake8 backend/ scraper/
black backend/ scraper/
cd web/frontend && npm run lint
```

---

## 🐛 Troubleshooting

### Scraper Issues

**"No **NUXT** in HTML"**

- Cause: `__NUXT__` is JavaScript function
- Solution: Use `document.write()` to execute JS

**Container hangs**

- Cause: Multiple containers running
- Solution: `docker ps | grep scraper | awk '{print $1}' | xargs docker kill`

**Old checkpoints**

- Solution: `rm data/state_*.json && rm -rf data/checkpoints/*`

**Proxy returns 0 cookies**

- Solution: Use `proxy=None` for FlareSolverr

### Bot Issues

**Webhook not receiving**

- Test: `stripe listen --forward-to localhost:8000/webhook/stripe`
- Trigger: `stripe trigger checkout.session.completed`

**Rate limit not working**

- Check: `SELECT messages_today FROM users WHERE telegram_id=...`
- Reset: `UPDATE users SET messages_today=0 WHERE telegram_id=...`

### Database Issues

**pgvector not found**

- Solution: Use `pgvector/pgvector:pg15` Docker image

**Connection refused**

- Solution: `docker compose up -d postgres && sleep 10`

---

## 📊 Performance & Scaling

### Current Performance

- **Scraper:** 50 pages/hour (~2,500 jobs/hour)
- **RAG Pipeline:** 15-30 min for 10,000 jobs
- **Bot:** 1-3s response time, 100+ concurrent users

### Scaling Strategies

**Horizontal (Scraper):**
Deploy 3 servers → 3× faster scraping

**Vertical (Backend):**
Upgrade to CPX42 (16 vCPU) → 2× faster embeddings

**Database:**
Add indexes, partition tables, enable caching

### Monitoring

```bash
docker compose logs -f backend
docker compose logs -f scraper
grep "ERROR" backend.log
```

---

## 📝 License

Proprietary software. All rights reserved.

---

## 👨‍💻 Author

**Martin** — [GitHub](https://github.com/MartinLilt)

---

## 🙏 Acknowledgments

- **FlareSolverr** — Cloudflare bypass
- **nodriver** — Chrome automation
- **sentence-transformers** — Embeddings
- **aiogram** — Telegram framework
- **Stripe** — Payments
- **Hetzner Cloud** — Infrastructure

---

## 📅 Changelog

### 2026-03-31 — FlareSolverr Success ✅

- Automated Cloudflare bypass
- Removed Xvfb dependency
- Added checkpoint system
- Tested: 250 jobs in 6 min
- Production ready 🚀

### 2026-03-15 — RAG Pipeline Complete

- 7-step pipeline implemented
- pgvector integration
- OpenAI profile naming

### 2026-03-01 — Bot Launch

- 3-tier subscription plans
- Stripe integration
- Google Sheets CRM

### 2026-02-15 — Project Init

- Monorepo structure
- Docker Compose setup
- Initial scraper prototype

---

**Happy Scraping! 🚀**
