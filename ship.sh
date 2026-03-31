#!/usr/bin/env bash
# =============================================================================
# ship.sh — build, push, and deploy in one command
#
# Usage:
#   bash ship.sh [backend|scraper|all] [--no-cache]
#
# Reads GHCR_USER, GHCR_TOKEN, BACKEND_SERVER_IP from .env (repo root).
#
# Examples:
#   bash ship.sh backend              # build + push + deploy backend
#   bash ship.sh scraper              # build + push + deploy scraper
#   bash ship.sh all                  # build + push + deploy everything
#   bash ship.sh backend --no-cache   # force full rebuild (no layer cache)
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-backend}"
NO_CACHE="${2:-}"

log() { echo ""; echo "▶ $*"; echo ""; }

log "STEP 1 — Build & push images"
bash "$REPO_ROOT/infra/deploy/push-images.sh" "$TARGET" $NO_CACHE

log "STEP 2 — Deploy on server"
bash "$REPO_ROOT/infra/deploy/deploy.sh" "$TARGET"

echo ""
echo "✅ Shipped: $TARGET"
