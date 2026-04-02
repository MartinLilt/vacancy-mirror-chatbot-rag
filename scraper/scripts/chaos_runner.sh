#!/bin/bash
# Chaos Scraper Runner — chaotic multi-category entry point for cron.
#
# Logic:
# 1. Check work day (Mon–Sat) and work hours (8:00–22:00)
# 2. Sleep random 0–N minutes inside the hour (looks human)
# 3. Run scrape-chaos: visits all 12 categories in random order,
#    random pages, remembers progress in /app/data/chaos_state.json
# 4. Stops after MAX_RUNTIME_MINUTES or at 22:00, whichever is first
# 5. Monday → reset state (fresh week)

set -e

# ── Config ────────────────────────────────────────────────────────────
START_HOUR=8
END_HOUR=22

DELAY_MIN=15
DELAY_MAX=90

# Max pages to visit per category per session (each page ≈ 50 jobs)
MAX_PAGES_PER_CAT=5

# Target jobs per category (overall, cumulative across sessions)
TARGET_PER_CAT=100

# Max session runtime (leaves ~10 min buffer before next hour)
MAX_RUNTIME_MINUTES=50

# Random startup delay range (seconds) — we sleep random(0, MAX_START_DELAY)
# at the beginning so each run starts at a different moment within the hour
MAX_START_DELAY=600   # up to 10 minutes

# Chrome persistent profile
USER_DATA_DIR="/app/data/chrome_profile"
mkdir -p "$USER_DATA_DIR"

# State file
STATE_FILE="/app/data/chaos_state.json"

# Lock file
LOCK_FILE="/app/data/chaos.lock"
STALE_LOCK_THRESHOLD=3600

echo "════════════════════════════════════════════════════"
echo "🌀  Chaos Runner — $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════"

# ── Work day check ────────────────────────────────────────────────────
WEEKDAY=$(date +%u)   # 1=Mon … 7=Sun
if [ "$WEEKDAY" -eq 7 ]; then
    echo "⏸️  Sunday — rest day, chaos scraper not running"
    exit 0
fi

# ── Work hours check ──────────────────────────────────────────────────
CURRENT_HOUR=$(date +%H | sed 's/^0//')
if [ "$CURRENT_HOUR" -lt "$START_HOUR" ] || [ "$CURRENT_HOUR" -ge "$END_HOUR" ]; then
    echo "⏰ Outside work hours (${START_HOUR}:00–${END_HOUR}:00), current: ${CURRENT_HOUR}:xx"
    exit 0
fi

echo "✅ Work day: $(date +%A) | Hour: ${CURRENT_HOUR}:xx"

# ── Lock ──────────────────────────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)))
    if [ "$LOCK_AGE" -lt "$STALE_LOCK_THRESHOLD" ]; then
        echo "🔒 Another chaos process is running (lock age: ${LOCK_AGE}s) — exiting"
        exit 0
    else
        echo "⚠️  Stale lock (${LOCK_AGE}s) — removing and continuing"
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
echo "🔓 Lock acquired (PID: $$)"
trap 'rm -f "$LOCK_FILE"; echo "🔓 Lock released"' EXIT INT TERM

# ── Monday: reset state for new week ─────────────────────────────────
RESET_FLAG=""
if [ "$WEEKDAY" -eq 1 ]; then
    echo "🗓️  Monday — new week, resetting chaos state"
    rm -f "$STATE_FILE"
    RESET_FLAG="--reset"
fi

# ── FlareSolverr health check ─────────────────────────────────────────
# FLARESOLVERR_URL может быть http://flaresolverr:8191/v1 (для API)
# Health endpoint всегда на /health (без /v1), поэтому отрезаем /v1
FLARESOLVERR_URL="${FLARESOLVERR_URL:-http://flaresolverr:8191}"
FLARESOLVERR_BASE="${FLARESOLVERR_URL%/v1}"
echo "🔍 Checking FlareSolverr at ${FLARESOLVERR_BASE}/health ..."
FS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${FLARESOLVERR_BASE}/health" 2>/dev/null || echo "000")
if [ "$FS_STATUS" != "200" ]; then
    echo "❌ FlareSolverr is not healthy (HTTP ${FS_STATUS}) — aborting this run"
    echo "   Fix: check 'docker compose logs flaresolverr' on the server"
    exit 1
fi
echo "✅ FlareSolverr healthy"

# ── Random startup delay ──────────────────────────────────────────────
START_DELAY=$((RANDOM % MAX_START_DELAY))
echo "😴 Sleeping ${START_DELAY}s before starting (chaos entry point)..."
sleep "$START_DELAY"
echo "⚡ Woke up at $(date '+%H:%M:%S') — launching chaos scraper"

# ── Recalculate remaining runtime after sleep ─────────────────────────
# Clamp max runtime so we don't run past END_HOUR
CURRENT_MINUTE=$(date +%M | sed 's/^0//')
CURRENT_HOUR_NOW=$(date +%H | sed 's/^0//')
MINUTES_TO_END=$(( (END_HOUR - CURRENT_HOUR_NOW) * 60 - CURRENT_MINUTE ))
SAFE_RUNTIME=$(( MINUTES_TO_END - 5 ))  # 5 min buffer

if [ "$SAFE_RUNTIME" -le 5 ]; then
    echo "⏰ Less than 10 minutes left before ${END_HOUR}:00 — skipping this iteration"
    exit 0
fi

if [ "$SAFE_RUNTIME" -lt "$MAX_RUNTIME_MINUTES" ]; then
    ACTUAL_RUNTIME=$SAFE_RUNTIME
else
    ACTUAL_RUNTIME=$MAX_RUNTIME_MINUTES
fi

echo "⏱️  Session runtime: ${ACTUAL_RUNTIME} min (safe window before ${END_HOUR}:00)"
echo "📋 Config:"
echo "   Pages/cat : ${MAX_PAGES_PER_CAT}"
echo "   Target/cat: ${TARGET_PER_CAT} jobs"
echo "   Delay     : ${DELAY_MIN}–${DELAY_MAX}s"
echo "   State file: ${STATE_FILE}"
echo "   Profile   : ${USER_DATA_DIR}"
echo ""

# ── Run chaos scraper ─────────────────────────────────────────────────
python3 -m scraper.cli scrape-chaos \
    --max-pages-per-cat "$MAX_PAGES_PER_CAT" \
    --target-per-cat    "$TARGET_PER_CAT" \
    --delay-min         "$DELAY_MIN" \
    --delay-max         "$DELAY_MAX" \
    --stop-at-hour      "$END_HOUR" \
    --max-runtime-minutes "$ACTUAL_RUNTIME" \
    --state-file        "$STATE_FILE" \
    --user-data-dir     "$USER_DATA_DIR" \
    --db-url            "$DATABASE_URL" \
    $RESET_FLAG

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ Chaos session finished successfully"
else
    echo ""
    echo "❌ Chaos session failed with exit code $EXIT_CODE"
fi

echo "════════════════════════════════════════════════════"
exit $EXIT_CODE
