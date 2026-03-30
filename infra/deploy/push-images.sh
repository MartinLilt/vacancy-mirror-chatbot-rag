#!/usr/bin/env bash
# =============================================================================
# push-images.sh — build & push both Docker images to ghcr.io
#
# Usage:
#   export GHCR_USER=<github_username>
#   export GHCR_TOKEN=<github_PAT_with_write:packages>
#   bash infra/deploy/push-images.sh
#
# Run this from the repo root before running provision.sh or deploy.sh.
# =============================================================================
set -euo pipefail

GHCR_USER="${GHCR_USER:?GHCR_USER is required}"
GHCR_TOKEN="${GHCR_TOKEN:?GHCR_TOKEN is required}"

BACKEND_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest"
SCRAPER_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest"
API_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-api:latest"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "Logging into ghcr.io ..."
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin

log "Building backend image ..."
docker build \
    --platform linux/amd64 \
    -t "${BACKEND_IMAGE}" \
    ./backend

log "Building scraper image ..."
docker build \
    --platform linux/amd64 \
    -t "${SCRAPER_IMAGE}" \
    ./scraper

log "Building web/api image ..."
docker build \
    --platform linux/amd64 \
    -t "${API_IMAGE}" \
    ./web/api

log "Pushing backend image ..."
docker push "${BACKEND_IMAGE}"

log "Pushing scraper image ..."
docker push "${SCRAPER_IMAGE}"

log "Pushing web/api image ..."
docker push "${API_IMAGE}"

log ""
log "=== Images pushed ==="
log "  ${BACKEND_IMAGE}"
log "  ${SCRAPER_IMAGE}"
log "  ${API_IMAGE}"
