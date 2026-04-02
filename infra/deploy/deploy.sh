#!/usr/bin/env bash
# =============================================================================
# deploy.sh — pull new images and restart services on the server
#
# Usage:
#   bash infra/deploy/deploy.sh [backend|scraper|all]
#
# Required env vars (or place in .env at repo root):
#   GHCR_USER          — GitHub username
#   GHCR_TOKEN         — GitHub PAT with read:packages scope
#   BACKEND_SERVER_IP  — IP of the backend server (e.g. 178.104.113.58)
#   SCRAPER_SERVER_IP  — IP of the scraper server  (e.g. 178.104.110.28)
#
# Examples:
#   bash infra/deploy/deploy.sh backend
#   bash infra/deploy/deploy.sh scraper
#   bash infra/deploy/deploy.sh all
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Load .env from repo root if present
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
    # shellcheck disable=SC1091
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

GHCR_TOKEN="${GHCR_TOKEN:?Set GHCR_TOKEN env var or add it to .env}"
GHCR_USER="${GHCR_USER:?Set GHCR_USER env var or add it to .env}"
BACKEND_SERVER_IP="${BACKEND_SERVER_IP:?Set BACKEND_SERVER_IP in .env}"
SCRAPER_SERVER_IP="${SCRAPER_SERVER_IP:?Set SCRAPER_SERVER_IP in .env}"

TARGET="${1:-backend}"   # backend | scraper | all

SSH_KEY_PATH="$HOME/.ssh/vacancy_mirror_deploy"
BACKEND_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest"
SCRAPER_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$TARGET" =~ ^(backend|scraper|all)$ ]] \
    || die "Unknown target '$TARGET'. Use: backend | scraper | all"

run_remote() {
    ssh -o StrictHostKeyChecking=no \
        -i "$SSH_KEY_PATH" \
        "root@${BACKEND_SERVER_IP}" "$@"
}

run_remote_scraper() {
    ssh -o StrictHostKeyChecking=no \
        -i "$SSH_KEY_PATH" \
        "root@${SCRAPER_SERVER_IP}" "$@"
}

# ---------------------------------------------------------------------------
# Redeploy backend (restarts the running container)
# ---------------------------------------------------------------------------
deploy_backend() {
    log "--- Redeploying backend on ${BACKEND_SERVER_IP} ---"
    run_remote \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"
    run_remote bash <<'REMOTE'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull backend
docker compose up -d --no-deps backend
echo "Backend container restarted."
docker logs vacancy-mirror-backend-1 --tail 20 2>&1 || true
REMOTE
    log "Backend redeployed."
}

# ---------------------------------------------------------------------------
# Redeploy scraper stack on Server 2
# - pull latest scraper image
# - recreate flaresolverr (to pick up env changes)
# - recreate scraper
# ---------------------------------------------------------------------------
deploy_scraper() {
    log "--- Redeploying scraper on ${SCRAPER_SERVER_IP} ---"
    run_remote_scraper \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"
    run_remote_scraper bash <<REMOTE
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull scraper
docker compose up -d --no-deps --force-recreate flaresolverr scraper
echo "Scraper stack recreated (flaresolverr + scraper)."
sleep 3
docker compose ps flaresolverr scraper
REMOTE
    log "Scraper redeployed on ${SCRAPER_SERVER_IP}."
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
log "=== Deploying: $TARGET ==="
case "$TARGET" in
    backend) deploy_backend ;;
    scraper) deploy_scraper ;;
    all)
        deploy_backend
        deploy_scraper
        ;;
esac
log "=== Deploy complete ==="
