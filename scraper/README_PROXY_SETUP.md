# Residential Proxy Setup (IPRoyal Sticky Sessions)

## Overview

This guide explains how to configure the scraper to use **IPRoyal Residential Proxies** with **24-hour sticky sessions** to bypass Cloudflare while maintaining session isolation from your personal Upwork account.

---

## Why Residential Proxy?

### Problem

- **Datacenter IP** (Hetzner VPS): Upwork flags suspicious activity, triggers Cloudflare challenges frequently.
- **Your personal IP**: Linking scraper activity to your Upwork account risks account reputation damage.

### Solution

- **Residential Proxy**: Real home/mobile IPs that look like legitimate users → Cloudflare passes automatically.
- **Sticky Session**: Same IP for 24 hours → Upwork sees consistent session, cookies stay valid longer.
- **Complete Isolation**: Your MacBook IP/cookies never touch the scraper.

---

## IPRoyal Setup (Recommended Provider)

### 1. Sign Up

- Go to: https://iproyal.com/residential-proxies/
- Plans:
  - **10 GB**: $65/month (covers ~25 categories)
  - **25 GB**: $145/month (covers 50+ categories with splits)

### 2. Get Sticky Session Credentials

After signup, go to Dashboard → Residential Proxies → **Session Control**:

```
Format: http://<username>:<password>@<geo>.residential.iproyal.com:12321

Example (24h sticky session, US geo):
http://username_country-US_session-scraper123_lifetime-1440:password@geo.iproyal.com:12321
```

**Parameters:**

- `username`: Your IPRoyal username (e.g., `martin`)
- `country-US`: Target country (US recommended for Upwork)
- `session-scraper123`: Unique session ID (keep same for 24h)
- `lifetime-1440`: Session lifetime in minutes (1440 = 24 hours)
- `password`: Your IPRoyal password

---

## Scraper Configuration

### Docker Compose Setup

Edit `docker-compose.yml`:

```yaml
services:
  scraper:
    environment:
      # Add proxy URL with sticky session
      PROXY_URL: "http://martin_country-US_session-upwork24h_lifetime-1440:YOUR_PASSWORD@geo.iproyal.com:12321"

      # Enable session persistence
      CHROME_USER_DATA_DIR: "/app/data/chrome_profile"

      # Cookie backup path
      COOKIE_BACKUP_PATH: "/app/data/session_cookies.json"

    volumes:
      # Persist Chrome session across restarts
      - ./data:/app/data
```

### Environment Variables

Create `.env` file in project root:

```bash
# IPRoyal Residential Proxy (24h sticky session)
PROXY_URL="http://USERNAME_country-US_session-scraper24h_lifetime-1440:PASSWORD@geo.iproyal.com:12321"

# Chrome session persistence
CHROME_USER_DATA_DIR="/app/data/chrome_profile"
COOKIE_BACKUP_PATH="/app/data/session_cookies.json"

# PostgreSQL
DATABASE_URL="postgresql://user:pass@db:5432/vacancy_mirror"
```

---

## How It Works

### Session Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Day 1 (00:00)                                               │
│ ├─ Scraper starts                                           │
│ ├─ Connects via IPRoyal proxy (IP: 203.0.113.45)           │
│ ├─ Passes Cloudflare automatically (residential IP)        │
│ ├─ Saves cookies to chrome_profile/                        │
│ └─ Saves backup to session_cookies.json                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Day 1 (06:00, 12:00, 18:00)                                 │
│ ├─ Cron jobs run                                            │
│ ├─ Reuses SAME IP (203.0.113.45) via sticky session        │
│ ├─ Loads cookies from chrome_profile/                      │
│ ├─ No Cloudflare challenge (same IP + valid cookies)       │
│ └─ Scrapes successfully 🎉                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Day 2 (00:00) — NEW 24h SESSION                             │
│ ├─ Sticky session expires (24h limit reached)              │
│ ├─ IPRoyal assigns NEW IP (203.0.113.78)                   │
│ ├─ Old cookies still valid (if <30 days old)               │
│ ├─ May get Cloudflare challenge (new IP)                   │
│ ├─ Scraper solves it automatically (stealth patches)       │
│ └─ Continues for next 24 hours with new IP                 │
└─────────────────────────────────────────────────────────────┘
```

### Why 24-Hour Sessions?

- **Longer than cron intervals**: 6-hour cron jobs reuse same IP throughout the day.
- **Balances cost vs stability**: Daily rotation prevents Upwork from flagging long-term residential IP abuse.
- **Cookie compatibility**: Most Upwork cookies expire after 30-90 days, so daily IP changes don't break sessions.

---

## Session Isolation (Your IP vs Scraper)

### Your Personal Workflow (MacBook)

```
Your MacBook (IP: 93.84.202.11)
├─ Browse Upwork manually (proposals, messages)
├─ Cookies stored in: ~/Library/Application Support/Google/Chrome/
└─ NEVER touches scraper's chrome_profile/
```

### Scraper Workflow (Hetzner VPS)

```
Hetzner VPS (IP: 178.104.113.58)
├─ Chrome connects via IPRoyal proxy (IP: 203.0.113.45)
├─ Cookies stored in: /opt/vacancy-mirror/data/chrome_profile/
├─ Backup stored in: /opt/vacancy-mirror/data/session_cookies.json
└─ NEVER sees your MacBook IP or cookies
```

**Zero Overlap:**

- Different IPs (yours vs residential proxy).
- Different cookie stores (MacBook Chrome vs server chrome_profile).
- Different user agents (your browser vs scraper's stealth patches).

---

## Rotating Sessions Daily

### Option 1: Cron Job (Automated)

Create `rotate_proxy_session.sh`:

```bash
#!/bin/bash
# Rotate IPRoyal session ID daily at midnight

# Generate random session ID
SESSION_ID="upwork-$(date +%Y%m%d)-$RANDOM"

# Update .env file
sed -i "s/session-[^_]*/session-$SESSION_ID/" /opt/vacancy-mirror/.env

# Restart scraper to pick up new session
docker-compose restart scraper

echo "Proxy session rotated: $SESSION_ID"
```

Add to crontab:

```cron
0 0 * * * /opt/vacancy-mirror/scraper/scripts/rotate_proxy_session.sh
```

### Option 2: Manual Rotation

Just change the `session-XXXXX` part in your `PROXY_URL`:

```bash
# Before (old session)
PROXY_URL="http://user_session-day1_lifetime-1440:pass@geo.iproyal.com:12321"

# After (new session)
PROXY_URL="http://user_session-day2_lifetime-1440:pass@geo.iproyal.com:12321"
```

Then restart:

```bash
docker-compose restart scraper
```

---

## Testing Proxy Connection

### 1. Check IP Address

```bash
docker-compose exec scraper python -c "
import urllib.request
proxy = urllib.request.ProxyHandler({
    'http': 'http://user_session-test_lifetime-1440:pass@geo.iproyal.com:12321',
    'https': 'http://user_session-test_lifetime-1440:pass@geo.iproyal.com:12321',
})
opener = urllib.request.build_opener(proxy)
response = opener.open('https://api.ipify.org?format=json')
print(response.read().decode())
"
```

Expected output:

```json
{"ip": "203.0.113.45"}  # Residential IP, NOT 178.104.113.58
```

### 2. Test Cloudflare Bypass

```bash
python -m scraper.cli scrape \
    --uid 531770282580668418 \
    --label "Web Dev" \
    --max-pages 1 \
    --user-data-dir ./data/chrome_profile \
    --proxy-url "http://user_session-test_lifetime-1440:pass@geo.iproyal.com:12321"
```

Expected behavior:

- ✅ Opens Upwork search page
- ✅ No Cloudflare challenge (passes automatically)
- ✅ Scrapes jobs successfully

---

## Cost Calculation

### Monthly Traffic

| Categories | Pages/cat | Total Pages | Traffic/Page | Monthly Traffic |
| ---------- | --------- | ----------- | ------------ | --------------- |
| 1 (test)   | 10        | 10          | 35 KB        | 0.33 GB         |
| 25 (L1+L2) | 34 avg    | 850         | 35 KB        | 8.4 GB          |
| 50 (all)   | 34 avg    | 1,700       | 35 KB        | 14.4 GB         |

### IPRoyal Pricing

| Plan  | Price/month | Traffic | Cost per GB | Best For              |
| ----- | ----------- | ------- | ----------- | --------------------- |
| 10 GB | $65         | 10 GB   | $6.50       | 25 categories (L1+L2) |
| 25 GB | $145        | 25 GB   | $5.80       | 50+ categories (full) |

**Recommendation:** Start with **10 GB plan** ($65/month) for 25 categories.

---

## Troubleshooting

### Cloudflare Still Blocks

**Symptoms:** "Just a moment..." page appears even with proxy.

**Causes:**

1. Proxy IP burned (Upwork flagged it).
2. Session ID reused too long (>30 days).
3. Cookies expired.

**Solutions:**

```bash
# 1. Rotate session immediately
# Edit docker-compose.yml: change session-XXX to session-YYY
docker-compose restart scraper

# 2. Clear old cookies
rm -rf data/chrome_profile/Default/Cookies
rm data/session_cookies.json

# 3. Restart scraper
docker-compose restart scraper
```

### Proxy Authentication Failed

**Symptoms:** `407 Proxy Authentication Required`

**Causes:**

- Wrong username/password.
- Incorrect proxy URL format.

**Solution:**

```bash
# Test credentials via curl
curl -x "http://user:pass@geo.iproyal.com:12321" https://api.ipify.org

# Should return residential IP, not error
```

### Session Expires Too Fast

**Symptoms:** New IP every hour instead of 24h.

**Cause:** `lifetime-XXX` parameter too low.

**Solution:**

```bash
# Check lifetime parameter (must be 1440 for 24h)
PROXY_URL="http://user_session-X_lifetime-1440:pass@..."
#                                    ^^^^ = 24 hours
```

---

## Migration from Phase 1 (No Proxy)

If you're currently running **Phase 1** (cookie persistence only, no proxy):

### Step 1: Buy IPRoyal Plan

- Sign up at https://iproyal.com/residential-proxies/
- Choose **10 GB** plan ($65/month)

### Step 2: Update Configuration

```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Add PROXY_URL env var:
environment:
  PROXY_URL: "http://user_session-upwork_lifetime-1440:pass@geo.iproyal.com:12321"
```

### Step 3: Clear Old Session (Optional)

```bash
# If cookies were created on Hetzner datacenter IP, clear them:
rm -rf data/chrome_profile/
rm data/session_cookies.json

# Let scraper create fresh session via residential proxy
```

### Step 4: Restart

```bash
docker-compose restart scraper
```

### Step 5: Test

```bash
# Run category inspection to verify proxy works
python -m scraper.cli inspect-category \
    --name "Web, Mobile & Software Dev" \
    --expected-uid 531770282580668418
```

Expected: No Cloudflare challenge, scraping works smoothly.

---

## Summary

✅ **Residential Proxy**: IPRoyal with US geo ($65/month for 10GB).  
✅ **Sticky Session**: Same IP for 24 hours (`lifetime-1440`).  
✅ **Session Isolation**: Your MacBook IP/cookies NEVER touch scraper.  
✅ **Cookie Persistence**: `chrome_profile/` + `session_cookies.json` backup.  
✅ **Daily Rotation**: Automatic session ID change every 24h (optional cron).  
✅ **Cloudflare Bypass**: Residential IP + stealth patches = 99% automation.

**Cost:** $65/month (25 categories) or $145/month (50+ categories).  
**Setup Time:** 10 minutes (add `PROXY_URL` to docker-compose.yml).  
**Maintenance:** Near-zero (automatic rotation, no manual intervention).

🚀 Ready to deploy? Update `PROXY_URL` in docker-compose.yml and restart!
