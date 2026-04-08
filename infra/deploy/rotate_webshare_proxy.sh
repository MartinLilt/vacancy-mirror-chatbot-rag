#!/usr/bin/env bash
# =============================================================================
# rotate_webshare_proxy.sh
# =============================================================================
# Автоматически обновляет PROXY_URL в scraper.env используя Webshare API.
#
# Что делает:
#   1. Дёргает Webshare API → получает актуальные username + password
#   2. Обновляет PROXY_URL в /etc/vacancy-mirror/scraper.env
#      Формат: http://username:password@p.webshare.io:80
#      (plain residential — без sticky session суффикса)
#   3. Перезапускает scraper контейнер
#
# Cron (запуск каждый день в 02:00):
#   0 2 * * * /etc/vacancy-mirror/rotate_webshare_proxy.sh >> /var/log/rotate_webshare_proxy.log 2>&1
#
# Установка:
#   scp infra/deploy/rotate_webshare_proxy.sh root@SERVER:/etc/vacancy-mirror/
#   ssh root@SERVER "chmod +x /etc/vacancy-mirror/rotate_webshare_proxy.sh"
#   ssh root@SERVER "echo '0 2 * * * /etc/vacancy-mirror/rotate_webshare_proxy.sh >> /var/log/rotate_webshare_proxy.log 2>&1' | crontab -l | cat - | crontab -"
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Source env vars from compose .env (contains WEBSHARE_API_KEY)
if [ -f /etc/vacancy-mirror/.env ]; then
    set -o allexport
    source /etc/vacancy-mirror/.env
    set +o allexport
fi
WEBSHARE_API_KEY="${WEBSHARE_API_KEY:?WEBSHARE_API_KEY not set in /etc/vacancy-mirror/.env}"
WEBSHARE_API_URL="https://proxy.webshare.io/api/v2/proxy/config/"
WEBSHARE_HOST="p.webshare.io"
WEBSHARE_PORT="80"

ENV_FILE="/etc/vacancy-mirror/scraper.env"
# Docker-compose читает переменные из .env (не из scraper.env)
# Поэтому обновляем оба файла
COMPOSE_ENV_FILE="/etc/vacancy-mirror/.env"
COMPOSE_FILE="/etc/vacancy-mirror/docker-compose.yml"
CONTAINER_NAME="scraper"

LOG_PREFIX="[$(date +'%Y-%m-%d %H:%M:%S')] rotate_webshare_proxy:"

# ---------------------------------------------------------------------------
# Функции
# ---------------------------------------------------------------------------
log()  { echo "$LOG_PREFIX $*"; }
die()  { echo "$LOG_PREFIX ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Получаем credentials из Webshare API
# ---------------------------------------------------------------------------
log "Fetching credentials from Webshare API..."

response=$(curl -sf \
    -H "Authorization: Token ${WEBSHARE_API_KEY}" \
    "${WEBSHARE_API_URL}") || die "Webshare API request failed"

WS_USERNAME=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['username'])")
WS_PASSWORD=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['password'])")

[[ -n "$WS_USERNAME" ]] || die "Empty username from Webshare API"
[[ -n "$WS_PASSWORD" ]] || die "Empty password from Webshare API"

log "Got credentials: username=${WS_USERNAME}, password=***"

# ---------------------------------------------------------------------------
# 2. Формируем PROXY_URL (plain residential — без sticky session суффикса)
#    Webshare plain residential принимает только: username:password
#    Суффикс -us-YYYYMMDD-HHMMSS → 400 Bad Request (client_connect_invalid_params)
# ---------------------------------------------------------------------------
NEW_PROXY_URL="http://${WS_USERNAME}:${WS_PASSWORD}@${WEBSHARE_HOST}:${WEBSHARE_PORT}"

log "New PROXY_URL: http://${WS_USERNAME}:***@${WEBSHARE_HOST}:${WEBSHARE_PORT}"

# ---------------------------------------------------------------------------
# 3. Обновляем оба env файла
# ---------------------------------------------------------------------------
update_proxy_in_file() {
    local file="$1"
    [[ -f "$file" ]] || { log "WARN: $file not found — skipping"; return; }
    cp "$file" "${file}.bak"
    if grep -q "^PROXY_URL=" "$file"; then
        sed -i "s|^PROXY_URL=.*|PROXY_URL=${NEW_PROXY_URL}|" "$file"
    else
        echo "PROXY_URL=${NEW_PROXY_URL}" >> "$file"
    fi
    local current
    current=$(grep "^PROXY_URL=" "$file" | cut -d'=' -f2-)
    [[ "$current" == "$NEW_PROXY_URL" ]] || die "Verification failed in $file"
    log "Updated PROXY_URL in $file"
}

update_proxy_in_file "$ENV_FILE"
update_proxy_in_file "$COMPOSE_ENV_FILE"

# ---------------------------------------------------------------------------
# 4. Перезапускаем scraper контейнер
# ---------------------------------------------------------------------------
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Restarting container: ${CONTAINER_NAME}..."
    cd /etc/vacancy-mirror
    docker compose up -d --force-recreate "${CONTAINER_NAME}" 2>&1 | tail -5
    log "Container restarted."
else
    log "WARN: Container '${CONTAINER_NAME}' not running — skipping restart"
fi

log "✅ Done. PROXY_URL=http://${WS_USERNAME}:***@${WEBSHARE_HOST}:${WEBSHARE_PORT}"
