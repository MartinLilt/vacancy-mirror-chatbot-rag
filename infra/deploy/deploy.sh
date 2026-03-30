#!/usr/bin/env bash
# =============================================================================
# deploy.sh — pull new images and restart services on existing servers
#
# Usage (after provision.sh ran once):
#   export HCLOUD_TOKEN=<token>
#   export GHCR_TOKEN=<github_PAT>
#   export GHCR_USER=<github_username>
#   bash infra/deploy/deploy.sh
#
# Workflow:
#   1. Run push-images.sh first to push the new images.
#   2. Run this script to pull and restart on both servers.
# =============================================================================
set -euo pipefail

HCLOUD_TOKEN="${HCLOUD_TOKEN:?HCLOUD_TOKEN is required}"
GHCR_TOKEN="${GHCR_TOKEN:?GHCR_TOKEN is required}"
GHCR_USER="${GHCR_USER:?GHCR_USER is required}"

SSH_KEY_PATH="$HOME/.ssh/vacancy_mirror_deploy"
BACKEND_SERVER="vacancy-mirror-backend"
SCRAPER_SERVER="vacancy-mirror-scraper"

BACKEND_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest"
SCRAPER_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest"

log() { echo "[$(date +%H:%M:%S)] $*"; }

server_ip() {
    hcloud server describe "$1" \
        --output format="{{.PublicNet.IPv4.IP}}"
}

run_remote() {
    local ip="$1"; shift
    ssh -o StrictHostKeyChecking=no \
        -i "$SSH_KEY_PATH" \
        "root@$ip" "$@"
}

# ---------------------------------------------------------------------------
# Redeploy backend
# ---------------------------------------------------------------------------
deploy_backend() {
    local ip
    ip=$(server_ip "$BACKEND_SERVER")
    log "--- Redeploying backend on $ip ---"

    run_remote "$ip" \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    run_remote "$ip" bash <<REMOTE
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull backend
docker compose up -d --no-deps backend
REMOTE

    log "Backend redeployed."
}

# ---------------------------------------------------------------------------
# Redeploy scraper (just pull image — cron will use it on next run)
# ---------------------------------------------------------------------------
deploy_scraper() {
    local ip
    ip=$(server_ip "$SCRAPER_SERVER")
    log "--- Updating scraper image on $ip ---"

    run_remote "$ip" \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    run_remote "$ip" "docker pull '${SCRAPER_IMAGE}'"
    log "Scraper image updated. Next cron run will use the new image."
}

main() {
    log "=== Deploying to Hetzner ==="
    deploy_backend
    deploy_scraper
    log "=== Deploy complete ==="
}

main "$@"
