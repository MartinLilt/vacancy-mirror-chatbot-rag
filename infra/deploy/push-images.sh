#!/usr/bin/env bash
# =============================================================================
# push-images.sh — build & push Docker images to ghcr.io
#
# Usage:
#   bash infra/deploy/push-images.sh [backend|scraper|all] [--no-cache]
#
# Required env vars (or place in .env at repo root):
#   GHCR_USER   — GitHub username (e.g. martinlilt)
#   GHCR_TOKEN  — GitHub PAT with write:packages scope
#
# Examples:
#   bash infra/deploy/push-images.sh backend
#   bash infra/deploy/push-images.sh all --no-cache
#   bash infra/deploy/push-images.sh scraper
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

GHCR_USER="${GHCR_USER:?Set GHCR_USER env var or add it to .env}"
GHCR_TOKEN="${GHCR_TOKEN:?Set GHCR_TOKEN env var or add it to .env}"

TARGET="${1:-all}"      # backend | scraper | all
NO_CACHE=""
if [[ "${2:-}" == "--no-cache" || "${1:-}" == "--no-cache" ]]; then
    NO_CACHE="--no-cache"
    [[ "$TARGET" == "--no-cache" ]] && TARGET="all"
fi

BACKEND_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest"
SCRAPER_IMAGE="ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$TARGET" =~ ^(backend|scraper|all)$ ]] \
    || die "Unknown target '$TARGET'. Use: backend | scraper | all"

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
log "Logging into ghcr.io as ${GHCR_USER} ..."
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin

# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------
build_backend() {
    log "Building backend image${NO_CACHE:+ (--no-cache)} ..."
    docker build \
        --platform linux/amd64 \
        ${NO_CACHE} \
        -t "${BACKEND_IMAGE}" \
        "$REPO_ROOT/backend"
    log "Backend image built."
}

build_scraper() {
    log "Building scraper image${NO_CACHE:+ (--no-cache)} ..."
    docker build \
        --platform linux/amd64 \
        ${NO_CACHE} \
        -t "${SCRAPER_IMAGE}" \
        "$REPO_ROOT/scraper"
    log "Scraper image built."
}

# ---------------------------------------------------------------------------
# Push helpers
# ---------------------------------------------------------------------------
push_backend() {
    log "Pushing backend image ..."
    docker push "${BACKEND_IMAGE}"
    log "Backend pushed: ${BACKEND_IMAGE}"
}

push_scraper() {
    log "Pushing scraper image ..."
    docker push "${SCRAPER_IMAGE}"
    log "Scraper pushed: ${SCRAPER_IMAGE}"
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
case "$TARGET" in
    backend)
        build_backend && push_backend
        ;;
    scraper)
        build_scraper && push_scraper
        ;;
    all)
        build_backend
        build_scraper
        push_backend
        push_scraper
        ;;
esac

log ""
log "=== Done ==="
