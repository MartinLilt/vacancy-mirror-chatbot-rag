#!/usr/bin/env bash
#
# Phase 2 Deployment Script
# Run this on your Hetzner VPS: bash deploy_phase2.sh
#

set -euo pipefail

echo "=== Phase 2 Deployment: Webshare Proxy + Session Persistence ==="

# 1. Update .env with Phase 2 configuration
echo "Step 1/5: Updating .env..."
cd /opt/vacancy-mirror

# Backup original .env
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

# Add Phase 2 environment variables
if ! grep -q "PROXY_URL=" .env; then
    echo "" >> .env
    echo "# Phase 2: Residential Proxy + Session Persistence" >> .env
    echo "PROXY_URL=http://yredwczd-1-country-US-session-upwork123:1500jnrpopto@p.webshare.io:80" >> .env
    echo "CHROME_USER_DATA_DIR=/app/data/chrome_profile" >> .env
    echo "COOKIE_BACKUP_PATH=/app/data/session_cookies.json" >> .env
    echo "✅ Added Phase 2 variables to .env"
else
    echo "⚠️  PROXY_URL already exists in .env - skipping"
fi

# 2. Deploy rotation script
echo "Step 2/5: Deploying rotation script..."
mkdir -p /opt/vacancy-mirror/scraper/scripts

cat > /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vacancy-mirror/.env"
SESSION_ID="upwork-$(date +%Y%m%d-%H%M%S)"

# Update PROXY_URL with new session ID
sed -i "s/session-[^:]*/session-${SESSION_ID}/" "$ENV_FILE"

echo "[$(date)] Rotated Webshare session to: ${SESSION_ID}"
EOF

chmod +x /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh
echo "✅ Rotation script deployed"

# 3. Setup cron job
echo "Step 3/5: Setting up cron job..."
mkdir -p /opt/vacancy-mirror/logs

CRON_LINE="*/30 * * * * /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh >> /opt/vacancy-mirror/logs/cron.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "rotate_webshare_session.sh"; then
    echo "⚠️  Cron job already exists - skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "✅ Cron job added (runs every 30 minutes)"
fi

# 4. Test proxy connectivity
echo "Step 4/5: Testing proxy connectivity..."
PROXY_URL="http://yredwczd-1-country-US-session-test:1500jnrpopto@p.webshare.io:80"
PROXY_IP=$(curl --proxy "$PROXY_URL" -s https://api.ipify.org || echo "FAILED")

if [[ "$PROXY_IP" == "FAILED" ]]; then
    echo "❌ Proxy test FAILED - check credentials"
    exit 1
else
    echo "✅ Proxy test PASSED - IP: $PROXY_IP (residential)"
fi

# 5. Restart scraper
echo "Step 5/5: Restarting scraper..."
cd /opt/vacancy-mirror
docker-compose restart scraper
echo "✅ Scraper restarted with Phase 2 configuration"

echo ""
echo "=== Phase 2 Deployment Complete! ==="
echo ""
echo "Next steps:"
echo "1. Run test scrape:"
echo "   docker-compose exec scraper python -m scraper.cli scrape \\"
echo "       --uid 531770282580668418 \\"
echo "       --label 'Web Dev' \\"
echo "       --max-pages 1 \\"
echo "       --delay-min 5 \\"
echo "       --delay-max 10"
echo ""
echo "2. Check cron logs:"
echo "   tail -f /opt/vacancy-mirror/logs/cron.log"
