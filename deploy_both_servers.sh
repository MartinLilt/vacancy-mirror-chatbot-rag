#!/usr/bin/env bash
#
# Deploy Phase 2 to BOTH servers
# - Backend server: 178.104.113.58 (Teecho "[$(date)] Rotated Webshaecho "Step 7/8: Updating docker-compose.yml..."
if grep echo "Step 3/4: Updating docker-compose.yml..."
if grep -q "build: ./backend" docker-compose.yml; then
    sed -i 's|build: ./backend|image: ghcr.io/'\$GHCR_USER'/vacancy-mirror-backend:latest|' docker-compose.yml
    echo "✅ docker-compose.yml updated to use ghcr.io image"
else
    echo "⚠️  docker-compose.yml already uses image"
fi

echo "Step 4/4: Restarting backend...": ./scraper" docker-compose.yml; then
    sed -i 's|build: ./scraper|image: ghcr.io/'\$GHCR_USER'/vacancy-mirror-scraper:latest|' docker-compose.yml
    echo "✅ docker-compose.yml updated to use ghcr.io image"
else
    echo "⚠️  docker-compose.yml already uses image"
fi

echo "Step 8/8: Restarting scraper..."n to: \${SESSION_ID}"
EOF

chmod +x "\$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh"
echo "✅ Rotation script created"

echo "Step 5/8: Setting up cron job..."
mkdir -p "\$PROJECT_DIR/logs"

CRON_LINE="*/30 * * * * \$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh >> \$PROJECT_DIR/logs/cron.log 2>&1", API, PostgreSQL)
# - Scraper server: 178.104.110.28 (Chrome, nodriver, scraping)
#

set -euo pipefail

# Load .env for GHCR credentials
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

GHCR_TOKEN="${GHCR_TOKEN:?Set GHCR_TOKEN in .env}"
GHCR_USER="${GHCR_USER:?Set GHCR_USER in .env}"

BACKEND_SERVER="root@178.104.113.58"
SCRAPER_SERVER="root@178.104.110.28"
PROJECT_DIR="/opt/vacancy-mirror"
SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"

WEBSHARE_PROXY="http://yredwczd-1-country-US-session-upwork123:1500jnrpopto@p.webshare.io:80"

# SSH wrapper with key authentication
ssh_backend() {
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$BACKEND_SERVER" "$@"
}

ssh_scraper() {
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SCRAPER_SERVER" "$@"
}

echo "=== Phase 2: Two-Server Deployment ==="
echo ""
echo "Backend server: $BACKEND_SERVER"
echo "Scraper server: $SCRAPER_SERVER"
echo ""

# ========================================================================
# PART 1: Deploy to SCRAPER server (178.104.110.28)
# ========================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PART 1: Deploying to SCRAPER server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh_scraper bash -s << ENDSCRAPER
set -euo pipefail

PROJECT_DIR="$PROJECT_DIR"
WEBSHARE_PROXY="$WEBSHARE_PROXY"
GHCR_TOKEN="$GHCR_TOKEN"
GHCR_USER="$GHCR_USER"

cd "\$PROJECT_DIR"

echo "Step 1/8: Logging into GitHub Container Registry..."
echo "\$GHCR_TOKEN" | docker login ghcr.io -u "\$GHCR_USER" --password-stdin

echo "Step 2/8: Backing up .env..."
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

echo "Step 3/8: Adding Phase 2 variables to .env..."
if ! grep -q "PROXY_URL=" .env; then
    cat >> .env << 'EOF'

# Phase 2: Webshare Residential Proxy + Session Persistence
PROXY_URL=http://yredwczd-1-country-US-session-upwork123:1500jnrpopto@p.webshare.io:80
CHROME_USER_DATA_DIR=/app/data/chrome_profile
COOKIE_BACKUP_PATH=/app/data/session_cookies.json
EOF
    echo "✅ Phase 2 variables added"
else
    echo "⚠️  PROXY_URL already exists, updating..."
    sed -i "s|^PROXY_URL=.*|PROXY_URL=\$WEBSHARE_PROXY|" .env
fi

echo "Step 4/8: Creating rotation script..."
mkdir -p "\$PROJECT_DIR/scraper/scripts"

cat > "\$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vacancy-mirror/.env"
SESSION_ID="upwork-$(date +%Y%m%d-%H%M%S)"

sed -i "s/session-[^:]*/session-${SESSION_ID}/" "$ENV_FILE"

echo "[$(date)] Rotated Webshare session to: ${SESSION_ID}"
EOF

chmod +x "$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh"
echo "✅ Rotation script created"

echo "Step 4/7: Setting up cron job..."
mkdir -p "$PROJECT_DIR/logs"

CRON_LINE="*/30 * * * * $PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh >> $PROJECT_DIR/logs/cron.log 2>&1"

if crontab -l 2>/dev/null | grep -q "rotate_webshare_session.sh"; then
    echo "⚠️  Cron job already exists, skipping"
else
    (crontab -l 2>/dev/null || echo "") | { cat; echo "\$CRON_LINE"; } | crontab -
    echo "✅ Cron job added (runs every 30 minutes)"
fi

echo "Step 6/8: Pulling latest scraper image from ghcr.io..."
docker pull ghcr.io/\$GHCR_USER/vacancy-mirror-scraper:latest

echo "Step 7/8: Updating docker-compose.yml..."
if grep -q "build: ./scraper" docker-compose.yml; then
    sed -i 's|build: ./scraper|image: ghcr.io/martinlilt/vacancy-mirror-scraper:latest|' docker-compose.yml
    echo "✅ docker-compose.yml updated to use ghcr.io image"
else
    echo "⚠️  docker-compose.yml already uses image"
fi

echo "Step 7/7: Restarting scraper..."
docker-compose restart scraper || docker-compose up -d scraper

echo ""
echo "✅ SCRAPER server deployment complete!"
echo ""
ENDSCRAPER

SCRAPER_EXIT=$?

if [ $SCRAPER_EXIT -ne 0 ]; then
    echo ""
    echo "❌ SCRAPER server deployment failed!"
    exit $SCRAPER_EXIT
fi

# ========================================================================
# PART 2: Deploy to BACKEND server (178.104.113.58)
# ========================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PART 2: Deploying to BACKEND server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh_backend bash -s << ENDBACKEND
set -euo pipefail

PROJECT_DIR="$PROJECT_DIR"
GHCR_TOKEN="$GHCR_TOKEN"
GHCR_USER="$GHCR_USER"

cd "\$PROJECT_DIR"

echo "Step 1/4: Logging into GitHub Container Registry..."
echo "\$GHCR_TOKEN" | docker login ghcr.io -u "\$GHCR_USER" --password-stdin

echo "Step 2/4: Pulling latest backend image from ghcr.io..."
docker pull ghcr.io/\$GHCR_USER/vacancy-mirror-backend:latest

echo "Step 3/4: Updating docker-compose.yml..."
if grep -q "build: ./backend" docker-compose.yml; then
    sed -i 's|build: ./backend|image: ghcr.io/martinlilt/vacancy-mirror-backend:latest|' docker-compose.yml
    echo "✅ docker-compose.yml updated to use ghcr.io image"
else
    echo "⚠️  docker-compose.yml already uses image"
fi

echo "Step 3/3: Restarting backend..."
docker-compose restart backend || docker-compose up -d backend

echo ""
echo "✅ BACKEND server deployment complete!"
echo ""
ENDBACKEND

BACKEND_EXIT=$?

if [ $BACKEND_EXIT -ne 0 ]; then
    echo ""
    echo "❌ BACKEND server deployment failed!"
    exit $BACKEND_EXIT
fi

# ========================================================================
# SUMMARY
# ========================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Phase 2 Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Scraper server (178.104.110.28):"
echo "   - Webshare proxy configured"
echo "   - Session rotation enabled (every 30 min)"
echo "   - Chrome session persistence active"
echo ""
echo "✅ Backend server (178.104.113.58):"
echo "   - Latest backend image deployed"
echo "   - Telegram bot restarted"
echo ""
echo "Next steps:"
echo "  1. Test scraper on 178.104.110.28:"
echo "     ssh $SCRAPER_SERVER"
echo "     cd $PROJECT_DIR"
echo "     docker-compose exec scraper python -m scraper.cli scrape \\"
echo "       --uid 531770282580668418 --label 'Web Dev' --max-pages 1"
echo ""
echo "  2. Monitor logs:"
echo "     ssh $SCRAPER_SERVER 'cd $PROJECT_DIR && docker-compose logs -f scraper'"
echo ""
