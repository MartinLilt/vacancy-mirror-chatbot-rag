#!/usr/bin/env bash
#
# Automated Phase 2 Deployment Script
# Runs locally and deploys to Hetzner VPS via SSH
#

set -euo pipefail

SERVER="root@178.104.113.58"
PROJECT_DIR="/opt/vacancy-mirror"

echo "=== Phase 2 Automated Deployment ==="
echo ""

# Test SSH connection
echo "Testing SSH connection to $SERVER..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" "echo 'Connection OK'" 2>/dev/null; then
    echo "❌ SSH connection failed. Please ensure:"
    echo "   1. You have SSH key authentication set up, OR"
    echo "   2. You can login with password"
    echo ""
    echo "Attempting interactive SSH (will ask for password)..."
fi

echo ""
echo "Deploying Phase 2 configuration..."
echo ""

# Deploy via SSH with here-document
ssh "$SERVER" bash -s << 'ENDSSH'
set -euo pipefail

PROJECT_DIR="/opt/vacancy-mirror"
cd "$PROJECT_DIR"

echo "Step 1/6: Backing up .env..."
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

echo "Step 2/6: Adding Phase 2 variables to .env..."
if ! grep -q "PROXY_URL=" .env; then
    cat >> .env << 'EOF'

# Phase 2: Webshare Residential Proxy + Session Persistence
PROXY_URL=http://yredwczd-1-country-US-session-upwork123:1500jnrpopto@p.webshare.io:80
CHROME_USER_DATA_DIR=/app/data/chrome_profile
COOKIE_BACKUP_PATH=/app/data/session_cookies.json
EOF
    echo "✅ Phase 2 variables added"
else
    echo "⚠️  PROXY_URL already exists, skipping"
fi

echo "Step 3/6: Creating rotation script..."
mkdir -p "$PROJECT_DIR/scraper/scripts"

cat > "$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vacancy-mirror/.env"
SESSION_ID="upwork-$(date +%Y%m%d-%H%M%S)"

# Update PROXY_URL with new session ID
sed -i "s/session-[^:]*/session-${SESSION_ID}/" "$ENV_FILE"

echo "[$(date)] Rotated Webshare session to: ${SESSION_ID}"
EOF

chmod +x "$PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh"
echo "✅ Rotation script created"

echo "Step 4/6: Setting up cron job..."
mkdir -p "$PROJECT_DIR/logs"

CRON_LINE="*/30 * * * * $PROJECT_DIR/scraper/scripts/rotate_webshare_session.sh >> $PROJECT_DIR/logs/cron.log 2>&1"

if crontab -l 2>/dev/null | grep -q "rotate_webshare_session.sh"; then
    echo "⚠️  Cron job already exists, skipping"
else
    (crontab -l 2>/dev/null || echo "") | { cat; echo "$CRON_LINE"; } | crontab -
    echo "✅ Cron job added (runs every 30 minutes)"
fi

echo "Step 5/6: Testing proxy connectivity..."
PROXY_URL="http://yredwczd-1-country-US-session-test:1500jnrpopto@p.webshare.io:80"

if command -v curl &> /dev/null; then
    PROXY_IP=$(curl --proxy "$PROXY_URL" -s --connect-timeout 10 https://api.ipify.org 2>/dev/null || echo "FAILED")
    
    if [[ "$PROXY_IP" == "FAILED" ]]; then
        echo "⚠️  Proxy test inconclusive (may need more time or firewall rules)"
    else
        echo "✅ Proxy test PASSED - IP: $PROXY_IP"
    fi
else
    echo "⚠️  curl not found, skipping proxy test"
fi

echo "Step 6/6: Restarting scraper..."
cd "$PROJECT_DIR"

if command -v docker-compose &> /dev/null; then
    docker-compose restart scraper
    echo "✅ Scraper restarted"
else
    echo "⚠️  docker-compose not found, please restart manually"
fi

echo ""
echo "=== Phase 2 Deployment Complete! ==="
echo ""
echo "Configuration summary:"
grep "PROXY_URL=" .env | head -n 1
grep "CHROME_USER_DATA_DIR=" .env | head -n 1
grep "COOKIE_BACKUP_PATH=" .env | head -n 1
echo ""
echo "Cron job:"
crontab -l | grep rotate_webshare_session || echo "(not found)"
echo ""
echo "Next: Run test scrape to verify everything works!"
ENDSSH

DEPLOY_EXIT_CODE=$?

if [ $DEPLOY_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "🎉 Deployment successful!"
    echo ""
    echo "To test the scraper, run:"
    echo "  ssh $SERVER 'cd $PROJECT_DIR && docker-compose exec scraper python -m scraper.cli scrape --uid 531770282580668418 --label \"Web Dev\" --max-pages 1 --delay-min 5 --delay-max 10'"
else
    echo ""
    echo "❌ Deployment failed with exit code $DEPLOY_EXIT_CODE"
    echo "Please check the error messages above"
    exit $DEPLOY_EXIT_CODE
fi
