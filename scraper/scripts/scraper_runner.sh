#!/bin/bash
# Scraper runner — main entry point for cron job.
#
# Logic:
# 1. Check if today is work day (Mon-Sat)
# 2. Check if current time is work hours (8:00-22:00)
# 3. Load checkpoint state
# 4. If Monday → reset state and DB
# 5. If week expired → wait until Monday
# 6. Detect level and calculate total pages
# 7. Resume from checkpoint page
# 8. Scrape until 22:00 or max pages reached

set -e

# Category to scrape (Web, Mobile & Software Dev)
CATEGORY_UID="${SCRAPER_CATEGORY_UID:-531770282580668418}"
CATEGORY_NAME="Web, Mobile & Software Dev"

# Work hours
START_HOUR=8
END_HOUR=22

# Delay between pages (seconds)
DELAY_MIN=30
DELAY_MAX=45

# For level 1 testing: 4 pages × 50 jobs = 200 jobs (2 lists × 100)
MAX_PAGES_TEST=4

# Lock file to prevent overlapping processes
LOCK_FILE="/app/data/scraper.lock"
STALE_LOCK_THRESHOLD=3600  # 1 hour in seconds (max runtime is 55 min)

# Random runtime: 40-55 minutes to guarantee finish before next hour
MIN_RUNTIME=40
MAX_RUNTIME=55

echo "════════════════════════════════════════════════════"
echo "🕷️  Scraper Runner — $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════"

# ──────────────────────────────────────────────────────
# Lock mechanism to prevent overlapping processes
# ──────────────────────────────────────────────────────

if [ -f "$LOCK_FILE" ]; then
    # Lock exists — check if it's stale
    LOCK_AGE=$(($(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)))
    
    if [ "$LOCK_AGE" -lt "$STALE_LOCK_THRESHOLD" ]; then
        echo "🔒 Another scraper process is running (lock age: ${LOCK_AGE}s)"
        echo "   Waiting for previous run to finish..."
        exit 0
    else
        echo "⚠️  Stale lock detected (age: ${LOCK_AGE}s > ${STALE_LOCK_THRESHOLD}s)"
        echo "   Removing stale lock and continuing..."
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock with current PID
echo $$ > "$LOCK_FILE"
echo "🔓 Lock acquired (PID: $$)"

# Trap to ensure lock is removed on exit
trap 'rm -f "$LOCK_FILE"; echo "🔓 Lock released"' EXIT INT TERM

# ──────────────────────────────────────────────────────
# Calculate random runtime limit (40-55 minutes)
# ──────────────────────────────────────────────────────

RUNTIME_MINUTES=$((MIN_RUNTIME + RANDOM % (MAX_RUNTIME - MIN_RUNTIME + 1)))
echo "⏱️  Max runtime for this iteration: ${RUNTIME_MINUTES} minutes"

# 1. Check work day (Mon-Sat)
WEEKDAY=$(date +%u)  # 1=Mon, 7=Sun
if [ "$WEEKDAY" -eq 7 ]; then
    echo "⏸️  Sunday — rest day, scraper not running"
    exit 0
fi

# 2. Check work hours (8:00-22:00)
CURRENT_HOUR=$(date +%H | sed 's/^0//')  # Remove leading zero
if [ "$CURRENT_HOUR" -lt "$START_HOUR" ] || [ "$CURRENT_HOUR" -ge "$END_HOUR" ]; then
    echo "⏰ Outside work hours ($START_HOUR:00-$END_HOUR:00), current: $CURRENT_HOUR:00"
    exit 0
fi

echo "✅ Work day: $(date +%A) (weekday $WEEKDAY)"
echo "✅ Work hours: $CURRENT_HOUR:00 (range $START_HOUR:00-$END_HOUR:00)"

# 3. Check if state file exists
STATE_FILE="/app/data/state_${CATEGORY_UID}.json"
if [ -f "$STATE_FILE" ]; then
    CURRENT_PAGE=$(jq -r '.current_page // 1' "$STATE_FILE")
    TOTAL_PAGES=$(jq -r '.total_pages // 0' "$STATE_FILE")
    WEEK_EXPIRED=$(jq -r '.week_expired // false' "$STATE_FILE")
    COMPLETED=$(jq -r '.completed // false' "$STATE_FILE")
    echo "📂 Found checkpoint: page $CURRENT_PAGE/$TOTAL_PAGES (expired=$WEEK_EXPIRED, completed=$COMPLETED)"
else
    CURRENT_PAGE=1
    TOTAL_PAGES=0
    WEEK_EXPIRED="false"
    COMPLETED="false"
    echo "🆕 No checkpoint — starting fresh"
fi

# 4. Monday → reset state
if [ "$WEEKDAY" -eq 1 ]; then
    echo "🗓️  Monday — new week, resetting state"
    rm -f "$STATE_FILE"
    CURRENT_PAGE=1
    WEEK_EXPIRED="false"
    COMPLETED="false"
    
    echo ""
    echo "🔍 Monday check: Verifying category UIDs and levels..."
    echo "   Running category inspection before main scrape..."
    echo ""
    
    # Run category check to verify UID and detect current level
    python -m scraper.cli inspect-category \
        --name "$CATEGORY_NAME" \
        --expected-uid "$CATEGORY_UID"
    
    INSPECT_EXIT=$?
    if [ $INSPECT_EXIT -ne 0 ]; then
        echo "⚠️  Category inspection failed, but continuing with scrape..."
    fi
    
    echo ""
    # Note: DB cleanup happens in Python code
fi

# 5. Week expired? → wait until Monday
if [ "$WEEK_EXPIRED" = "true" ]; then
    echo "⏹️  Week expired (Saturday passed, incomplete) — waiting for Monday"
    exit 0
fi

# 6. Already completed? → wait until Monday
if [ "$COMPLETED" = "true" ]; then
    echo "✅ Already completed this week — waiting for Monday"
    exit 0
fi

# 7. Run scraper
echo "▶️  Starting scraper..."
echo "   Category: $CATEGORY_NAME ($CATEGORY_UID)"
echo "   Start page: $CURRENT_PAGE"
echo "   Max pages: $MAX_PAGES_TEST (level 1 test)"
echo "   Delay: ${DELAY_MIN}-${DELAY_MAX} sec"
echo "   Stop at: ${END_HOUR}:00"
echo "   Runtime limit: ${RUNTIME_MINUTES} minutes"
echo ""

python -m scraper.cli scrape \
    --uid "$CATEGORY_UID" \
    --label "$CATEGORY_NAME" \
    --start-page "$CURRENT_PAGE" \
    --max-pages "$MAX_PAGES_TEST" \
    --delay-min "$DELAY_MIN" \
    --delay-max "$DELAY_MAX" \
    --stop-at-hour "$END_HOUR" \
    --max-runtime-minutes "$RUNTIME_MINUTES" \
    --db-url "$DATABASE_URL"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ Scraper finished successfully"
else
    echo ""
    echo "❌ Scraper failed with exit code $EXIT_CODE"
fi

echo "════════════════════════════════════════════════════"
exit $EXIT_CODE
