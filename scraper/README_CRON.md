# Scraper — Cron-Based Autonomous Container

## Overview

The scraper runs autonomously with a cron daemon inside the container. No external orchestration needed.

## Architecture

```
scraper container
  └─ cron daemon (runs at container start)
      └─ cron job (every hour, 8:00-22:00, Mon-Sat)
          └─ scraper_runner.sh
              └─ python -m scraper.cli scrape
```

## Files

- `entrypoint.sh` — Starts cron daemon
- `crontab` — Cron schedule (hourly 8-22, Mon-Sat)
- `scripts/scraper_runner.sh` — Main logic (work day check, time check, checkpoint)
- `src/scraper/scheduler.py` — Work hours, level detection
- `src/scraper/state.py` — Checkpoint state machine
- `src/scraper/cli.py` — CLI with new args (--start-page, --delay-min, --stop-at-hour)

## How It Works

### Weekly Lifecycle

**Monday 8:00 AM:**

- Cron starts `scraper_runner.sh`
- **🔍 FIRST: Category inspection** — verifies UID and detects current level
  ```bash
  python -m scraper.cli inspect-category \
      --name "Web, Mobile & Software Dev" \
      --expected-uid "531770282580668418"
  ```

  - Checks if `category2_uid` changed on Upwork
  - Reads current total job count
  - Determines level (1-4)
  - Logs warning if UID mismatch
- Script resets state (new week)
- Clears old DB data
- Starts from page 1
- Scrapes until 22:00 (e.g., 20 pages done)
- Saves checkpoint: `current_page: 20`

**Tuesday 8:00 AM:**

- Cron starts again
- Loads checkpoint → continues from page 21
- Scrapes until 22:00 (e.g., +15 pages = 35 total)
- Saves checkpoint: `current_page: 35`

**...(continues Wed-Sat)...**

**Saturday 22:00:**

- Reached 45/50 pages
- Week not complete but time's up

**Sunday:**

- Cron does NOT run (rest day)
- Week marked as expired

**Monday 8:00 AM (next week):**

- Cycle repeats (reset → start from page 1)

### Smart Features

✅ **Autonomous** — No external triggers needed  
✅ **Work hours** — Only runs 8:00-22:00 by IP region  
✅ **Work days** — Monday-Saturday, rests on Sunday  
✅ **Checkpoint** — Saves after each page, resumes on restart  
✅ **Human-like delays** — Random 30-45 sec between pages  
✅ **Time-aware** — Stops at 22:00 even mid-scrape  
✅ **Week expiration** — If Saturday passes incomplete → wait until Monday  
✅ **Lock mechanism** — Prevents overlapping processes (stale lock cleanup after 2h)  
✅ **Runtime limit** — Each iteration runs 40-55 minutes (random) to guarantee no overlap

## Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SCRAPER_CATEGORY_UID=531770282580668418  # Web Dev category
CHROME_PATH=/usr/bin/chromium
```

## Running Locally

```bash
docker-compose up scraper
# Will start cron, logs to /var/log/scraper.log
```

Check logs:

```bash
docker-compose exec scraper tail -f /var/log/scraper.log
```

Manual trigger (for testing):

```bash
docker-compose exec scraper /app/scripts/scraper_runner.sh
```

## Configuration

### Level 1 Test (Current)

- **Target:** 4 pages × 50 jobs = 200 jobs (2 lists × 100)
- **Delay:** 30-45 seconds between pages
- **Hours:** 8:00-22:00
- **Days:** Monday-Saturday

### Future Levels

- **Level 1:** 2500 jobs (50 pages)
- **Level 2:** 5000 jobs (100 pages)
- **Level 3:** 5-25k jobs
- **Level 4:** 25k+ jobs

## State Files

Checkpoints stored in `/app/data/`:

```
/app/data/
  ├─ state_531770282580668418.json  # Checkpoint
  └─ scraper.lock                     # Process lock (active during scrape)
```

Example state:

```json
{
  "category_uid": "531770282580668418",
  "category_name": "Web, Mobile & Software Dev",
  "level": 1,
  "total_pages": 4,
  "current_page": 2,
  "started_at": "2026-03-31",
  "last_run": "2026-03-31T15:30:00",
  "completed": false,
  "week_expired": false
}
```

## Lock Mechanism

**Prevents overlapping processes:**

- Before starting scrape → checks `/app/data/scraper.lock`
- If lock exists and fresh (< 1 hour) → exits (another process running or recently crashed)
- If lock is stale (> 1 hour) → removes and continues (assumes crashed, resumes from checkpoint)
- Creates lock with PID → runs scrape → removes lock on exit

**Runtime limit:**

- Each iteration runs **40-55 minutes** (randomized)
- Guarantees completion before next cron trigger (e.g., 8:00 → 8:47 → ready for 9:00)

**Crash recovery:**

- If scraper crashes (e.g., 8:15 on page 7) → lock remains
- Next hour (9:00) → lock age = 45 min → still fresh → waits
- Following hour (10:00) → lock age = 1h 45min → stale → removes lock, resumes from page 7 checkpoint

**Note:** Stale lock threshold = 1 hour (slightly more than max runtime of 55 min). This ensures that if a process doesn't complete within expected time, it's considered crashed and will be restarted at next opportunity.

## Deployment

1. Build image:

   ```bash
   bash ship.sh scraper
   ```

2. Container starts automatically with cron

3. Check logs on server:
   ```bash
   ssh root@178.104.113.58 -i ~/.ssh/vacancy_mirror_deploy
   docker logs -f vacancy-mirror-scraper-1
   ```

## Next Steps (TODO)

- [ ] Dynamic level detection (based on category job count)
- [ ] IP-based timezone detection
- [ ] Proxy rotation for rate limiting
- [ ] Multi-category parallel scraping
- [ ] Metrics & monitoring
