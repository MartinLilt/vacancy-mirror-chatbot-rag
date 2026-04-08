#!/usr/bin/env bash
set -euo pipefail

source .env 2>/dev/null ||true

GHCR_TOKEN="${GHCR_TOKEN:?Missing GHCR_TOKEN}"
GHCR_USER="${GHCR_USER:?Missing GHCR_USER}"
BACKEND_SERVER="root@178.104.113.58"
SCRAPER_SERVER="root@178.104.110.28"
PROJECT_DIR="/opt/vacancy-mirror"
SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"
PROXY="${PROXY_URL:-}"

echo "=== Phase 2 Deployment ==="
echo "Scraper: $SCRAPER_SERVER | Backend: $BACKEND_SERVER"
echo ""

# Deploy to scraper
echo "--- Scraper Server ---"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SCRAPER_SERVER" "
set -euo pipefail
cd $PROJECT_DIR
echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin
docker pull ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest
docker-compose up -d --no-deps scraper
echo '✅ Scraper updated'
"

# Deploy to backend
echo ""
echo "--- Backend Server ---"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$BACKEND_SERVER" "
set -euo pipefail
cd $PROJECT_DIR
echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin
docker pull ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest
docker-compose up -d --no-deps backend
echo '✅ Backend updated'
"

echo ""
echo "🎉 Done!"
