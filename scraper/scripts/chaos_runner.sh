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

# Ensure we use the python3 from the Docker base image (python:3.13-slim),
# not the system python3 pulled in by 'apt-get install chromium'.
# Cron runs with a minimal PATH (/usr/bin first), so we must be explicit.
export PATH=/usr/local/bin:$PATH

set -e

# ── Truncate log to prevent unbounded growth ──────────────────────────────
# Keep last 5000 lines.  Runs before every session so the file stays
# manageable even after weeks of 15 runs/day.
LOG_FILE="/var/log/scraper.log"
if [ -f "$LOG_FILE" ]; then
  LOG_LINES=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
  if [ "$LOG_LINES" -gt 10000 ]; then
    tail -n 5000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    echo "🧹 Log truncated: ${LOG_LINES} → 5000 lines"
  fi
fi

# ── Recover env vars from PID 1 (supervisord) when running under cron ────────
# Cron executes with a minimal environment and does NOT inherit the container's
# env vars set by docker-compose.  We read them from /proc/1/environ (the env
# of supervisord, which *does* have them because docker-compose injects them at
# container start).  Same technique as collect_proxy_usage_runner.sh.
_read_proc_env() {
  tr '\0' '\n' < /proc/1/environ | grep -m1 "^${1}=" | cut -d= -f2- || true
}

if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(_read_proc_env DATABASE_URL)"
  export DATABASE_URL
fi
if [ -z "${PROXY_URL:-}" ]; then
  PROXY_URL="$(_read_proc_env PROXY_URL)"
  export PROXY_URL
fi
if [ -z "${FLARESOLVERR_URL:-}" ]; then
  FLARESOLVERR_URL="$(_read_proc_env FLARESOLVERR_URL)"
  export FLARESOLVERR_URL
fi
if [ -z "${CHROME_PATH:-}" ]; then
  # Try env first, then fall back to the Debian chromium package location.
  CHROME_PATH="$(_read_proc_env CHROME_PATH)"
  if [ -z "$CHROME_PATH" ]; then
    CHROME_PATH="/usr/bin/chromium"
  fi
  export CHROME_PATH
fi

# Fail fast if DATABASE_URL is still missing — no point running without DB.
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR chaos_runner: DATABASE_URL is not set (checked env + /proc/1/environ)"
  exit 1
fi

# ── Config ────────────────────────────────────────────────────────────
START_HOUR=8
END_HOUR=22

DELAY_MIN=15
DELAY_MAX=90

# Max pages to visit per category per session (each page ≈ 50 jobs)
MAX_PAGES_PER_CAT=5

# Target jobs per category (overall, cumulative across sessions)
TARGET_PER_CAT=5000

# Max session runtime (leaves ~10 min buffer before next hour)
MAX_RUNTIME_MINUTES=50

# Random startup delay range (seconds) — we sleep random(0, MAX_START_DELAY)
# at the beginning so each run starts at a different moment within the hour
MAX_START_DELAY=600   # up to 10 minutes

# Chrome persistent profile
USER_DATA_DIR="/app/data/chrome_profile"
mkdir -p "$USER_DATA_DIR"

# Remove stale Chrome Singleton locks left by previous container incarnations.
# Chrome refuses to start if these point to a hostname that no longer exists.
rm -f "$USER_DATA_DIR/SingletonLock" \
      "$USER_DATA_DIR/SingletonCookie" \
      "$USER_DATA_DIR/SingletonSocket" 2>/dev/null

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
