#!/usr/bin/env bash
# =============================================================================
# nuke_and_redeploy.sh — Incident response: wipe all containers/images,
# upload fresh credentials, redeploy from clean GHCR images.
#
# ⚠️  PRESERVES Docker named volumes (postgres-data, grafana-data, etc.)
# ⚠️  DESTROYS all containers, images, networks, build cache
#
# Usage:
#   bash infra/deploy/nuke_and_redeploy.sh [backend|scraper|all]
#
# Prerequisites:
#   - .env at repo root with rotated credentials
#   - SSH key at ~/.ssh/vacancy_mirror_deploy
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Load .env
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

BACKEND_IP="${BACKEND_SERVER_IP:-178.104.113.58}"
SCRAPER_IP="${SCRAPER_SERVER_IP:-178.104.110.28}"
SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"
SSH_PORT="${SSH_PORT:-2222}"
TARGET="${1:-all}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

ssh_backend() {
    ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "root@${BACKEND_IP}" "$@"
}
ssh_scraper() {
    ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "root@${SCRAPER_IP}" "$@"
}
scp_backend() {
    scp -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" "$1" "root@${BACKEND_IP}:$2"
}
scp_scraper() {
    scp -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" "$1" "root@${SCRAPER_IP}:$2"
}

# =============================================================================
# BACKEND SERVER
# =============================================================================
nuke_backend() {
    log "========== BACKEND SERVER ($BACKEND_IP) =========="

    # --- Step 1: Pre-wipe sanity check ---
    log "[backend] Listing volumes BEFORE wipe..."
    ssh_backend "docker volume ls"

    log "[backend] Quick DB check..."
    ssh_backend "docker exec \$(docker ps -qf name=postgres) pg_isready -U app -d vacancy_mirror 2>/dev/null || echo 'Postgres not running (OK if already stopped)'"

    # --- Step 2: Stop everything ---
    log "[backend] Stopping all compose stacks..."
    ssh_backend bash <<'REMOTE'
set -euo pipefail

# Main stack
if [ -f /etc/vacancy-mirror/docker-compose.yml ]; then
    cd /etc/vacancy-mirror && docker compose down --remove-orphans 2>/dev/null || true
fi

# Chatwoot stack (find it)
for f in /etc/chatwoot/docker-compose.yml /etc/vacancy-mirror/chatwoot-docker-compose.yml; do
    if [ -f "$f" ]; then
        docker compose -f "$f" down --remove-orphans 2>/dev/null || true
    fi
done

# Kill any stragglers
docker rm -f $(docker ps -aq) 2>/dev/null || true
REMOTE

    # --- Step 3: Nuke images, cache, networks (NOT volumes) ---
    log "[backend] Nuking all images, build cache, networks..."
    ssh_backend "docker system prune -a -f"

    log "[backend] Verifying volumes survived..."
    ssh_backend "docker volume ls"

    # --- Step 4: Upload fresh backend.env ---
    log "[backend] Uploading fresh backend.env..."
    local tmp_env
    tmp_env=$(mktemp)
    cat > "$tmp_env" <<ENV
DB_PASSWORD=${DB_PASSWORD}
POSTGRES_PASSWORD=${DB_PASSWORD}
DB_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/vacancy_mirror
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_DROP_PENDING_UPDATES=${TELEGRAM_DROP_PENDING_UPDATES:-true}
GOOGLE_SHEETS_ID=${GOOGLE_SHEETS_ID}
GOOGLE_SERVICE_ACCOUNT_JSON=${GOOGLE_SERVICE_ACCOUNT_JSON}
CHATWOOT_BASE_URL=${CHATWOOT_BASE_URL}
CHATWOOT_ACCOUNT_ID=${CHATWOOT_ACCOUNT_ID}
CHATWOOT_INBOX_ID=${CHATWOOT_INBOX_ID}
CHATWOOT_API_ACCESS_TOKEN=${CHATWOOT_API_ACCESS_TOKEN}
CHATWOOT_WEBHOOK_TOKEN=${CHATWOOT_WEBHOOK_TOKEN}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
SCRAPER_API_KEY=${SCRAPER_API_KEY}
GRAFANA_BACKEND_PASSWORD=${GRAFANA_BACKEND_PASSWORD}
GRAFANA_BACKEND_ROOT_URL=${GRAFANA_BACKEND_ROOT_URL}
ASSISTANT_INFER_URLS=http://assistant-infer-1:8090,http://assistant-infer-2:8090,http://assistant-infer-3:8090
ENV
    ssh_backend "mkdir -p /etc/vacancy-mirror"
    scp_backend "$tmp_env" "/etc/vacancy-mirror/backend.env"
    rm -f "$tmp_env"

    # --- Step 5: Upload fresh docker-compose.yml ---
    log "[backend] Uploading fresh docker-compose.yml..."
    local tmp_compose
    tmp_compose=$(mktemp)
    sed "s|\${GHCR_USER}|${GHCR_USER}|g" \
        "$REPO_ROOT/infra/deploy/docker-compose.backend.yml" > "$tmp_compose"
    scp_backend "$tmp_compose" "/etc/vacancy-mirror/docker-compose.yml"
    rm -f "$tmp_compose"

    # Upload supporting files
    scp_backend "$REPO_ROOT/infra/deploy/nginx.conf" "/etc/vacancy-mirror/nginx.conf"
    ssh_backend "mkdir -p /etc/vacancy-mirror/db"
    scp_backend "$REPO_ROOT/infra/db/init.sql" "/etc/vacancy-mirror/db/init.sql"

    # Upload Grafana backend provisioning (datasources + dashboards)
    log "[backend] Uploading grafana-backend provisioning..."
    ssh_backend "mkdir -p /etc/vacancy-mirror/grafana-backend/provisioning"
    scp -r -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" \
        "$REPO_ROOT/infra/monitoring/grafana-backend/provisioning/." \
        "root@${BACKEND_IP}:/etc/vacancy-mirror/grafana-backend/provisioning"

    # --- Step 6: GHCR login, pull, start ---
    log "[backend] Logging into GHCR and pulling fresh images..."
    ssh_backend "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"
    ssh_backend bash <<'REMOTE'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull
docker compose up -d
sleep 5
echo "--- Container status ---"
docker compose ps
echo "--- Postgres check ---"
docker compose exec -T postgres pg_isready -U app -d vacancy_mirror || echo "WARN: postgres not ready yet"
echo "--- Backend logs (last 20) ---"
docker compose logs backend --tail 20 2>&1 || true
REMOTE

    # --- Step 7: Update DB password inside Postgres ---
    log "[backend] Updating DB password inside running Postgres..."
    ssh_backend "docker compose -f /etc/vacancy-mirror/docker-compose.yml exec -T postgres psql -U app -d vacancy_mirror -c \"ALTER USER app PASSWORD '${DB_PASSWORD}';\"" || log "WARN: DB password update failed — may need manual fix"

    log "========== BACKEND SERVER DONE =========="
}

# =============================================================================
# SCRAPER SERVER
# =============================================================================
nuke_scraper() {
    log "========== SCRAPER SERVER ($SCRAPER_IP) =========="

    # --- Step 1: Pre-wipe sanity check ---
    log "[scraper] Listing volumes BEFORE wipe..."
    ssh_scraper "docker volume ls"

    # --- Step 2: Stop everything ---
    log "[scraper] Stopping all compose stacks..."
    ssh_scraper bash <<'REMOTE'
set -euo pipefail
if [ -f /etc/vacancy-mirror/docker-compose.yml ]; then
    cd /etc/vacancy-mirror && docker compose down --remove-orphans 2>/dev/null || true
fi
docker rm -f $(docker ps -aq) 2>/dev/null || true
REMOTE

    # --- Step 3: Nuke images, cache, networks (NOT volumes) ---
    log "[scraper] Nuking all images, build cache, networks..."
    ssh_scraper "docker system prune -a -f"

    log "[scraper] Verifying volumes survived..."
    ssh_scraper "docker volume ls"

    # --- Step 4: Upload fresh .env ---
    log "[scraper] Uploading fresh .env..."
    local tmp_env
    tmp_env=$(mktemp)
    cat > "$tmp_env" <<ENV
DB_PASSWORD=${DB_PASSWORD}
PROXY_URL=${PROXY_URL}
SCRAPER_API_KEY=${SCRAPER_API_KEY}
WEBSHARE_API_KEY=${WEBSHARE_API_KEY}
FLARESOLVERR_PROXY_URL=${FLARESOLVERR_PROXY_URL:-}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
ENV
    ssh_scraper "mkdir -p /etc/vacancy-mirror"
    scp_scraper "$tmp_env" "/etc/vacancy-mirror/.env"
    rm -f "$tmp_env"

    # --- Step 5: Upload fresh docker-compose.yml ---
    log "[scraper] Uploading fresh docker-compose.yml..."
    scp_scraper "$REPO_ROOT/infra/deploy/docker-compose.server2.yml" "/etc/vacancy-mirror/docker-compose.yml"

    # Upload supporting files
    ssh_scraper "mkdir -p /etc/vacancy-mirror/db"
    scp_scraper "$REPO_ROOT/infra/db/init.sql" "/etc/vacancy-mirror/db/init.sql"
    scp_scraper "$REPO_ROOT/infra/monitoring/prometheus.yml" "/etc/vacancy-mirror/prometheus.yml"

    # Upload Grafana provisioning (datasources + dashboards)
    log "[scraper] Uploading grafana provisioning..."
    ssh_scraper "mkdir -p /etc/vacancy-mirror/grafana/provisioning"
    scp -r -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" \
        "$REPO_ROOT/infra/monitoring/grafana/provisioning/." \
        "root@${SCRAPER_IP}:/etc/vacancy-mirror/grafana/provisioning"

    # --- Step 6: GHCR login, pull, start ---
    log "[scraper] Logging into GHCR and pulling fresh images..."
    ssh_scraper "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"
    ssh_scraper bash <<'REMOTE'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull
docker compose up -d
sleep 5
echo "--- Container status ---"
docker compose ps
echo "--- Postgres check ---"
docker compose exec -T postgres pg_isready -U app -d vacancy_mirror || echo "WARN: postgres not ready yet"
echo "--- Scraper logs (last 20) ---"
docker compose logs scraper --tail 20 2>&1 || true
REMOTE

    # --- Step 7: Update DB password inside Postgres ---
    log "[scraper] Updating DB password inside running Postgres..."
    ssh_scraper "docker compose -f /etc/vacancy-mirror/docker-compose.yml exec -T postgres psql -U app -d vacancy_mirror -c \"ALTER USER app PASSWORD '${DB_PASSWORD}';\"" || log "WARN: DB password update failed — may need manual fix"

    log "========== SCRAPER SERVER DONE =========="
}

# =============================================================================
# Host-level security checks (both servers)
# =============================================================================
check_host_security() {
    local ip="$1" name="$2"
    log "[$name] Checking host-level security on $ip..."
    ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "root@${ip}" bash <<'REMOTE'
echo "=== Cron jobs ==="
ls -la /etc/cron.d/ 2>/dev/null || true
crontab -l 2>/dev/null || echo "(no root crontab)"

echo ""
echo "=== SSH authorized_keys ==="
cat /root/.ssh/authorized_keys 2>/dev/null | wc -l
echo "keys found"

echo ""
echo "=== Listening ports ==="
ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || true

echo ""
echo "=== Suspicious processes ==="
ps aux | grep -E '(crypto|miner|xmr|kinsing)' | grep -v grep || echo "(none found)"
REMOTE
}

# =============================================================================
# RUN
# =============================================================================
log "=== INCIDENT RESPONSE: Nuke & Redeploy ($TARGET) ==="
log "⚠️  This will DESTROY all containers/images but KEEP data volumes"
echo ""
read -p "Are you sure? Type YES to continue: " confirm
[[ "$confirm" == "YES" ]] || die "Aborted."

case "$TARGET" in
    backend)
        nuke_backend
        check_host_security "$BACKEND_IP" "backend"
        ;;
    scraper)
        nuke_scraper
        check_host_security "$SCRAPER_IP" "scraper"
        ;;
    all)
        nuke_backend
        nuke_scraper
        check_host_security "$BACKEND_IP" "backend"
        check_host_security "$SCRAPER_IP" "scraper"
        ;;
    *)
        die "Unknown target '$TARGET'. Use: backend | scraper | all"
        ;;
esac

log ""
log "=== INCIDENT RESPONSE COMPLETE ==="
log ""
log "Post-deploy checklist:"
log "  1. Verify Telegram bot responds: send /start"
log "  2. Verify Stripe webhook: check Stripe Dashboard for successful delivery"
log "  3. Verify Chatwoot: open https://www.app.vacancy-mirror.com/"
log "  4. Verify scraper API: ssh scraper → curl http://127.0.0.1:8000/docs"
log "  5. Check Grafana dashboards on both servers"
log "  6. Review host security output above for any anomalies"
log ""
log "  If DB password mismatch errors appear, run manually on each server:"
log "    docker exec -it <postgres> psql -U app -d vacancy_mirror -c \"ALTER USER app PASSWORD '<new_pass>';\""

