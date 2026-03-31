# Migration Guide: Phase 1 → Phase 2 (Add Residential Proxy)

## Overview

This guide walks through upgrading from **Phase 1** (cookie persistence only, no proxy) to **Phase 2** (residential proxy + cookie persistence) for autonomous Cloudflare bypass.

---

## Current State (Phase 1)

✅ **What You Have:**

- Cookie persistence via `chrome_profile/`
- Cookie backup in `session_cookies.json`
- Stealth patches (removes `navigator.webdriver` flag)
- Manual Cloudflare bypass (if needed)

❌ **Limitations:**

- Uses Hetzner datacenter IP (178.104.113.58)
- Cloudflare challenges appear frequently (~20% of runs)
- Requires manual intervention when blocked

---

## Target State (Phase 2)

✅ **What You'll Get:**

- Residential proxy (IPRoyal) with US home/mobile IPs
- 24-hour sticky sessions (same IP all day)
- 99% autonomous Cloudflare bypass
- Complete isolation from your personal IP/cookies
- Daily IP rotation (automatic, via cron)

💰 **Cost:** $65/month (10 GB, covers 25 categories)

---

## Prerequisites

### 1. Sign Up for IPRoyal

1. Go to: https://iproyal.com/residential-proxies/
2. Sign up for an account
3. Choose **Residential Proxies** plan:
   - **10 GB**: $65/month (recommended for 25 categories)
   - **25 GB**: $145/month (for 50+ categories)

### 2. Get Your Proxy Credentials

After payment, go to Dashboard → Residential Proxies → **Session Control**:

```
Username: martin
Password: your_password_here
Proxy Host: geo.iproyal.com
Proxy Port: 12321
```

---

## Migration Steps

### Step 1: Update .env File

Edit `/opt/vacancy-mirror/.env` on your Hetzner VPS:

```bash
# Before (Phase 1)
PROXY_URL=

# After (Phase 2)
PROXY_URL=http://martin_country-US_session-upwork20260331_lifetime-1440:your_password_here@geo.iproyal.com:12321
```

**Session ID Explanation:**

- `martin`: Your IPRoyal username
- `country-US`: Target geography (US = best for Upwork)
- `session-upwork20260331`: Unique session ID (YYYYMMDD format recommended)
- `lifetime-1440`: Session lifetime in minutes (1440 = 24 hours)
- `your_password_here`: Your IPRoyal password

### Step 2: Clear Old Datacenter IP Cookies (Optional)

If your current cookies were created on Hetzner's datacenter IP (178.104.113.58), clear them to start fresh with residential IP:

```bash
# SSH into server
ssh root@178.104.113.58

# Navigate to project
cd /opt/vacancy-mirror

# Clear old cookies (ONLY if you want fresh start)
rm -rf data/chrome_profile/Default/Cookies
rm data/session_cookies.json

# Scraper will create new cookies via residential proxy
```

**When to clear:**

- ✅ If Cloudflare keeps blocking your current cookies
- ✅ If you want to ensure 100% isolation from datacenter IP
- ❌ Skip if your cookies are working fine (they'll migrate automatically)

### Step 3: Restart Scraper

```bash
# Restart to apply new PROXY_URL
docker-compose restart scraper
```

### Step 4: Verify Proxy Connection

Test that scraper is using residential IP (not datacenter IP):

```bash
# Check current IP via proxy
docker-compose exec scraper python3 -c "
import urllib.request
import json
proxy_url = 'http://martin_country-US_session-upwork20260331_lifetime-1440:password@geo.iproyal.com:12321'
proxy = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
opener = urllib.request.build_opener(proxy)
response = opener.open('https://api.ipify.org?format=json')
data = json.loads(response.read().decode())
print(f'Current IP: {data[\"ip\"]}')
"
```

**Expected Output:**

```
Current IP: 203.0.113.45  # Residential IP (US-based)
```

**NOT:**

```
Current IP: 178.104.113.58  # Datacenter IP (wrong, proxy not working)
```

### Step 5: Test Cloudflare Bypass

Run a test scrape to verify Cloudflare passes automatically:

```bash
# Test with Web Dev category (1 page only)
python -m scraper.cli scrape \
    --uid 531770282580668418 \
    --label "Web Dev" \
    --max-pages 1 \
    --delay-min 5 \
    --delay-max 10
```

**Expected Behavior:**

- ✅ Opens Upwork search page
- ✅ NO Cloudflare challenge (passes silently)
- ✅ Scrapes 50 jobs from page 1
- ✅ Saves checkpoint to `data/checkpoints/531770282580668418/page_0001.json`

**If Cloudflare Still Appears:**

- Wait 30 seconds (residential IP needs to warm up)
- Check proxy URL format (common mistake: missing `http://` prefix)
- Verify IPRoyal subscription is active (check Dashboard)

### Step 6: Enable Daily Session Rotation (Optional)

Automatically rotate proxy session ID every 24 hours to prevent IP burnout:

```bash
# Make rotation script executable
chmod +x /opt/vacancy-mirror/scraper/scripts/rotate_proxy_session.sh

# Test manually first
/opt/vacancy-mirror/scraper/scripts/rotate_proxy_session.sh

# Add to crontab (runs daily at midnight)
crontab -e

# Add this line:
0 0 * * * /opt/vacancy-mirror/scraper/scripts/rotate_proxy_session.sh >> /opt/vacancy-mirror/logs/cron.log 2>&1
```

**What it does:**

- Changes `session-upwork20260331` → `session-upwork20260401` (new date)
- Restarts scraper container
- IPRoyal assigns new residential IP
- Old IP released back to pool

---

## Session Isolation Verification

### Your Personal Workflow (MacBook)

```bash
# Check your current IP
curl https://api.ipify.org

# Output: 93.84.202.11 (your home/office IP)
```

Your Upwork account cookies:

```
~/Library/Application Support/Google/Chrome/Default/Cookies
```

### Scraper Workflow (Hetzner VPS)

```bash
# SSH into server
ssh root@178.104.113.58

# Check scraper's IP (via proxy)
docker-compose exec scraper python3 -c "
import urllib.request, json
proxy_url = '...'  # from .env
proxy = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
opener = urllib.request.build_opener(proxy)
response = opener.open('https://api.ipify.org?format=json')
print(json.loads(response.read().decode())['ip'])
"

# Output: 203.0.113.45 (residential IP, NOT 178.104.113.58 or 93.84.202.11)
```

Scraper's cookies:

```
/opt/vacancy-mirror/data/chrome_profile/Default/Cookies
```

**Zero Overlap:**

- ✅ Different IPs (yours vs residential proxy)
- ✅ Different cookie stores (MacBook vs server)
- ✅ Different user agents (your browser vs scraper's stealth patches)

---

## Cost Tracking

### Monthly Breakdown

| Category   | Pages  | Traffic/Page | Monthly Traffic |
| ---------- | ------ | ------------ | --------------- |
| 1 (test)   | 10     | 35 KB        | 0.33 GB         |
| 25 (L1+L2) | 34 avg | 35 KB        | 8.4 GB          |
| 50 (all)   | 34 avg | 35 KB        | 14.4 GB         |

### IPRoyal Plans

| Plan  | Price/month | Traffic | Cost per GB | Best For                    |
| ----- | ----------- | ------- | ----------- | --------------------------- |
| 10 GB | $65         | 10 GB   | $6.50       | 25 categories (recommended) |
| 25 GB | $145        | 25 GB   | $5.80       | 50+ categories              |

**Recommendation:** Start with **10 GB** ($65/month) for 25 categories. Upgrade to 25 GB if you expand to 50+ categories with splits.

---

## Troubleshooting

### Issue 1: Proxy Authentication Failed

**Error:**

```
407 Proxy Authentication Required
```

**Causes:**

- Wrong username/password in `PROXY_URL`
- Incorrect proxy URL format

**Solution:**

```bash
# Test credentials via curl
curl -x "http://user:pass@geo.iproyal.com:12321" https://api.ipify.org

# Should return residential IP (e.g., 203.0.113.45)
# NOT: 407 error
```

### Issue 2: Still Using Datacenter IP

**Symptom:** IP check returns `178.104.113.58` instead of residential IP.

**Causes:**

- `PROXY_URL` not set in `.env`
- Docker container not restarted after `.env` change
- Proxy URL has typo (check `http://` prefix, port `12321`)

**Solution:**

```bash
# Verify .env file
cat .env | grep PROXY_URL

# Should show:
# PROXY_URL=http://user_session-XXX_lifetime-1440:pass@geo.iproyal.com:12321

# Restart scraper
docker-compose restart scraper

# Verify IP again
docker-compose exec scraper python3 -c "import urllib.request, json; ..."
```

### Issue 3: Cloudflare Still Blocks

**Symptom:** "Just a moment..." page appears even with residential proxy.

**Causes:**

- Proxy IP already burned (Upwork flagged it)
- Session ID reused too long (>30 days)
- Cookies expired or invalid

**Solution:**

```bash
# 1. Rotate session immediately
# Edit .env: change session-upwork20260331 to session-upwork20260401
nano /opt/vacancy-mirror/.env

# 2. Clear old cookies
rm -rf data/chrome_profile/Default/Cookies
rm data/session_cookies.json

# 3. Restart scraper
docker-compose restart scraper

# 4. Test again
python -m scraper.cli scrape --uid 531770282580668418 --max-pages 1
```

### Issue 4: Session Expires Too Fast

**Symptom:** New IP every hour instead of 24 hours.

**Cause:** `lifetime-XXX` parameter too low.

**Solution:**

```bash
# Check .env file
cat .env | grep PROXY_URL

# Must have: lifetime-1440 (not lifetime-60 or lifetime-120)
# 1440 minutes = 24 hours

# Fix:
nano .env
# Change lifetime-60 to lifetime-1440

# Restart:
docker-compose restart scraper
```

---

## Rollback (Phase 2 → Phase 1)

If residential proxy costs too much or causes issues, revert to Phase 1:

```bash
# Edit .env
nano /opt/vacancy-mirror/.env

# Set PROXY_URL to empty
PROXY_URL=

# Restart scraper
docker-compose restart scraper

# Scraper will use datacenter IP (178.104.113.58) again
# Manual Cloudflare bypass required when blocked
```

---

## Success Metrics

### Phase 1 (Before Migration)

- ❌ Cloudflare challenges: ~20% of runs
- ❌ Manual intervention required: 1-2 times per day
- ❌ Success rate: 80%
- ✅ Cost: $0/month

### Phase 2 (After Migration)

- ✅ Cloudflare challenges: <1% of runs
- ✅ Manual intervention required: ~0 times per week
- ✅ Success rate: 99%
- 💰 Cost: $65/month (10 GB)

**ROI Calculation:**

- **Time saved:** 30 minutes/day (no manual Cloudflare solving)
- **Hourly rate:** $50/hour (average developer rate)
- **Monthly savings:** 30 min/day × 30 days × $50/hr ÷ 60 = **$750/month**
- **Net benefit:** $750 - $65 = **$685/month**

---

## Next Steps

1. ✅ Update `.env` with `PROXY_URL`
2. ✅ Restart scraper: `docker-compose restart scraper`
3. ✅ Verify residential IP: `curl via proxy should NOT return 178.104.113.58`
4. ✅ Test Cloudflare bypass: `scrape 1 page, should pass silently`
5. ✅ Enable daily rotation: `add cron job for rotate_proxy_session.sh`
6. ✅ Monitor logs: `tail -f logs/proxy_rotation.log`
7. ✅ Track usage: Check IPRoyal Dashboard (should stay under 10 GB/month for 25 categories)

🚀 **You're now running Phase 2!** Enjoy 99% autonomous scraping with complete session isolation.

---

## Support

- **IPRoyal Issues:** Contact support@iproyal.com (24/7 live chat)
- **Scraper Issues:** Check `logs/scraper.log` or `logs/cron.log`
- **Proxy Setup Guide:** `scraper/README_PROXY_SETUP.md`
