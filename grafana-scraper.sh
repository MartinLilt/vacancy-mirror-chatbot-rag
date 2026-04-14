#!/usr/bin/env bash
# =========================================================
# grafana-scraper.sh — single command to access Grafana
# on the scraper server via SSH tunnel
#
# Usage: bash grafana-scraper.sh
# =========================================================

SCRAPER_IP="89.167.27.149"
SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"
SSH_PORT=2222

echo "🔌 Killing existing tunnels on ports 3000 and 8000..."
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

echo "🚇 Opening SSH tunnels..."
echo "   localhost:3000 → Grafana"
echo "   localhost:8000 → Scraper API"
echo ""

# Open browser after 3 seconds (give the tunnel time to come up)
(sleep 3 && open "http://localhost:3000") &

ssh -i "$SSH_KEY" \
    -p "$SSH_PORT" \
    -L 3000:127.0.0.1:3000 \
    -L 8000:127.0.0.1:8000 \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    root@"$SCRAPER_IP"

echo "🔌 Tunnel closed."

