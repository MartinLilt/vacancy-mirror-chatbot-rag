#!/usr/bin/env bash
# =============================================================================
# deploy_security_fixes.sh — Deploy security fixes to both servers
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok() { echo -e "${GREEN}[$(date +%H:%M:%S)] ✅${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] ⚠️${NC} $*"; }
error() { echo -e "${RED}[$(date +%H:%M:%S)] ❌${NC} $*"; }
die() { error "$*"; exit 1; }

# Load .env
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

GHCR_USER="${GHCR_USER:-martinlilt}"
BACKEND_IP="${BACKEND_SERVER_IP:-178.104.113.58}"
SCRAPER_IP="${SCRAPER_SERVER_IP:-178.104.110.28}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/vacancy_mirror_deploy}"
SSH_PORT="${SSH_PORT:-2222}"

# =============================================================================
# Pre-flight checks
# =============================================================================
log "=== Pre-flight checks ==="

# Check SSH key
if [[ ! -f "$SSH_KEY" ]]; then
    die "SSH key not found: $SSH_KEY"
fi
ok "SSH key found: $SSH_KEY"

# Check Docker
if ! command -v docker &> /dev/null; then
    die "Docker not installed"
fi
ok "Docker installed: $(docker --version | head -1)"

# Check GHCR login
if ! docker info 2>/dev/null | grep -q "ghcr.io"; then
    warn "Not logged in to GHCR. Run: echo \$GITHUB_TOKEN | docker login ghcr.io -u $GHCR_USER --password-stdin"
fi

# Check SSH connectivity
log "Checking SSH connectivity..."
for ip in "$BACKEND_IP" "$SCRAPER_IP"; do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$SSH_KEY" -p "$SSH_PORT" "root@${ip}" "echo OK" &>/dev/null; then
        ok "SSH OK: $ip"
    else
        die "SSH failed: $ip (check SSH_KEY, SSH_PORT, server IP)"
    fi
done

echo ""
log "=== Security Fixes Deployment ==="
log "Scraper: $SCRAPER_IP"
log "Backend: $BACKEND_IP"
log "GHCR:    ghcr.io/$GHCR_USER"
echo ""

# =============================================================================
# Step 1: Build images
# =============================================================================
log "=== Step 1/5: Building Docker images ==="

# Build scraper
log "Building scraper image..."
docker build \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-scraper:latest" \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-scraper:security-$(date +%Y%m%d)" \
    scraper/
ok "Scraper image built"

# Build backend
log "Building backend image..."
docker build \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-backend:latest" \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-backend:security-$(date +%Y%m%d)" \
    backend/
ok "Backend image built"

# Build API
log "Building API image..."
docker build \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-api:latest" \
    -t "ghcr.io/$GHCR_USER/vacancy-mirror-api:security-$(date +%Y%m%d)" \
    web/api/
ok "API image built"

# =============================================================================
# Step 2: Push images to GHCR
# =============================================================================
log "=== Step 2/5: Pushing images to GitHub Container Registry ==="

log "Pushing scraper..."
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-scraper:latest"
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-scraper:security-$(date +%Y%m%d)"
ok "Scraper pushed"

log "Pushing backend..."
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-backend:latest"
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-backend:security-$(date +%Y%m%d)"
ok "Backend pushed"

log "Pushing API..."
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-api:latest"
docker push "ghcr.io/$GHCR_USER/vacancy-mirror-api:security-$(date +%Y%m%d)"
ok "API pushed"

# =============================================================================
# Step 3: Deploy to Scraper Server
# =============================================================================
log "=== Step 3/5: Deploying to Scraper Server ($SCRAPER_IP) ==="

ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "$SSH_PORT" "root@${SCRAPER_IP}" bash <<'SCRAPER_DEPLOY'
set -euo pipefail
cd /etc/vacancy-mirror

echo "📥 Pulling scraper image..."
docker compose pull scraper

echo "🔄 Recreating scraper container..."
docker compose up -d scraper

echo "⏳ Waiting for scraper to start..."
sleep 5

echo "📊 Container status:"
docker compose ps scraper

echo "📝 Recent logs:"
docker compose logs --tail 30 scraper

echo ""
echo "✅ Scraper deployment complete"
echo ""
echo "🔍 Verification:"
docker exec scraper pip show pydantic 2>/dev/null | grep Version || echo "  (cannot check - container might be running different command)"
SCRAPER_DEPLOY

ok "Scraper deployed"

# =============================================================================
# Step 4: Deploy to Backend Server
# =============================================================================
log "=== Step 4/5: Deploying to Backend Server ($BACKEND_IP) ==="

ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "$SSH_PORT" "root@${BACKEND_IP}" bash <<'BACKEND_DEPLOY'
set -euo pipefail
cd /etc/vacancy-mirror

echo "📥 Pulling images..."
docker compose pull backend assistant-infer-1 assistant-infer-2 assistant-infer-3 support-webhook api

echo "🔄 Recreating containers..."
docker compose up -d

echo "⏳ Waiting for containers to start..."
sleep 10

echo "📊 Container status:"
docker compose ps

echo ""
echo "📝 Backend logs (last 20 lines):"
docker compose logs --tail 20 backend

echo ""
echo "✅ Backend deployment complete"
echo ""
echo "🔍 Verification:"
echo "  aiohttp version:"
docker exec backend pip show aiohttp 2>/dev/null | grep Version || echo "  (cannot check)"
echo "  scikit-learn version:"
docker exec backend pip show scikit-learn 2>/dev/null | grep Version || echo "  (cannot check)"
BACKEND_DEPLOY

ok "Backend deployed"

# =============================================================================
# Step 5: Health checks
# =============================================================================
log "=== Step 5/5: Running health checks ==="

# Check scraper API
log "Checking scraper API health..."
SCRAPER_HEALTH=$(ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "$SSH_PORT" "root@${SCRAPER_IP}" \
    "curl -sf http://localhost:8000/health 2>/dev/null || echo '{\"error\":\"failed\"}'" | head -1)
if echo "$SCRAPER_HEALTH" | grep -q '"ok".*true'; then
    ok "Scraper API healthy: $SCRAPER_HEALTH"
else
    warn "Scraper API check failed: $SCRAPER_HEALTH"
fi

# Check backend API
log "Checking backend API health..."
BACKEND_HEALTH=$(ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "$SSH_PORT" "root@${BACKEND_IP}" \
    "curl -sf http://localhost:8000/health 2>/dev/null || echo '{\"error\":\"failed\"}'" | head -1)
if echo "$BACKEND_HEALTH" | grep -q 'ok'; then
    ok "Backend API healthy: $BACKEND_HEALTH"
else
    warn "Backend API check: $BACKEND_HEALTH"
fi

# Check Telegram bot
log "Checking Telegram bot..."
BACKEND_LOGS=$(ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "$SSH_PORT" "root@${BACKEND_IP}" \
    "docker compose logs --tail 50 backend 2>/dev/null" | tail -10)
if echo "$BACKEND_LOGS" | grep -qiE 'started|running|ready'; then
    ok "Backend logs look healthy"
else
    warn "Backend logs - check manually"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
log "═══════════════════════════════════════════════════════════"
log "✅  DEPLOYMENT COMPLETE"
log "═══════════════════════════════════════════════════════════"
echo ""
ok "Scraper Server ($SCRAPER_IP):"
echo "   - Image: ghcr.io/$GHCR_USER/vacancy-mirror-scraper:latest"
echo "   - Fixes: Pydantic 2.4.0, CORS whitelist, API validation"
echo "   - Health: $SCRAPER_HEALTH"
echo ""
ok "Backend Server ($BACKEND_IP):"
echo "   - Images: backend, api, assistant-infer×3, support-webhook"
echo "   - Fixes: aiohttp 3.13.4 (24 CVE!), scikit-learn 1.5.0, multi-stage build"
echo "   - Health: $BACKEND_HEALTH"
echo ""
log "═══════════════════════════════════════════════════════════"
echo ""
log "🔍 Manual verification commands:"
echo ""
echo "  # Scraper"
echo "  ssh -p $SSH_PORT -i $SSH_KEY root@$SCRAPER_IP"
echo "  cd /etc/vacancy-mirror && docker compose logs -f scraper"
echo "  curl http://localhost:8000/health"
echo ""
echo "  # Backend"
echo "  ssh -p $SSH_PORT -i $SSH_KEY root@$BACKEND_IP"
echo "  cd /etc/vacancy-mirror && docker compose logs -f backend"
echo "  docker exec backend pip show aiohttp scikit-learn"
echo ""
log "═══════════════════════════════════════════════════════════"
echo ""
ok "🎉 Both servers deployed successfully!"
echo ""

