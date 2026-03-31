#!/bin/bash
# ---------------------------------------------------------------------------
# Rotate IPRoyal proxy session ID daily
#
# Purpose:
#   - Changes proxy session ID to get a fresh residential IP every 24h
#   - Prevents Upwork from flagging long-term residential IP usage
#   - Balances cost (sticky session) vs anonymity (daily rotation)
#
# Usage:
#   1. Make executable: chmod +x rotate_proxy_session.sh
#   2. Test manually: ./rotate_proxy_session.sh
#   3. Add to crontab: 0 0 * * * /path/to/rotate_proxy_session.sh
#
# Schedule:
#   Runs daily at 00:00 (midnight) server time
#
# What it does:
#   - Generates new session ID: upwork-YYYYMMDD-RANDOM
#   - Updates PROXY_URL in .env file (replaces session-XXX part)
#   - Restarts scraper container to apply new session
#
# Example:
#   Before: session-upwork20260330
#   After:  session-upwork20260331-12345
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_DIR="/opt/vacancy-mirror"
ENV_FILE="$PROJECT_DIR/.env"
LOG_FILE="$PROJECT_DIR/logs/proxy_rotation.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

rotate_session() {
    # Check if .env exists
    if [[ ! -f "$ENV_FILE" ]]; then
        log "ERROR: .env file not found at $ENV_FILE"
        exit 1
    fi

    # Check if PROXY_URL is set
    if ! grep -q "^PROXY_URL=" "$ENV_FILE"; then
        log "ERROR: PROXY_URL not found in .env"
        exit 1
    fi

    # Check if PROXY_URL is empty (Phase 1 - no proxy)
    current_proxy=$(grep "^PROXY_URL=" "$ENV_FILE" | cut -d'=' -f2)
    if [[ -z "$current_proxy" ]]; then
        log "INFO: PROXY_URL is empty (Phase 1 mode), skipping rotation"
        exit 0
    fi

    # Generate new session ID
    new_session="upwork-$(date +%Y%m%d)-$RANDOM"
    log "INFO: Generating new session ID: $new_session"

    # Replace session ID in .env file
    # Pattern: session-XXXXX → session-YYYYMMDD-RANDOM
    sed -i.bak "s/session-[^_]*/session-$new_session/" "$ENV_FILE"

    # Verify replacement succeeded
    if grep -q "session-$new_session" "$ENV_FILE"; then
        log "SUCCESS: Updated PROXY_URL with new session: $new_session"
    else
        log "ERROR: Failed to update PROXY_URL, restoring backup"
        mv "$ENV_FILE.bak" "$ENV_FILE"
        exit 1
    fi

    # Clean up backup
    rm -f "$ENV_FILE.bak"
}

restart_scraper() {
    log "INFO: Restarting scraper container to apply new session..."
    
    cd "$PROJECT_DIR" || {
        log "ERROR: Failed to cd to $PROJECT_DIR"
        exit 1
    }

    if docker-compose restart scraper >> "$LOG_FILE" 2>&1; then
        log "SUCCESS: Scraper restarted successfully"
    else
        log "ERROR: Failed to restart scraper container"
        exit 1
    fi
}

verify_new_ip() {
    log "INFO: Waiting 10s for scraper to initialize..."
    sleep 10

    log "INFO: Verifying new IP address..."
    
    # Extract proxy URL from .env
    proxy_url=$(grep "^PROXY_URL=" "$ENV_FILE" | cut -d'=' -f2)
    
    # Check IP via proxy
    new_ip=$(docker-compose exec -T scraper python3 -c "
import urllib.request
import json
import sys
proxy_url = '$proxy_url'
if not proxy_url:
    sys.exit(1)
proxy = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
opener = urllib.request.build_opener(proxy)
response = opener.open('https://api.ipify.org?format=json')
data = json.loads(response.read().decode())
print(data['ip'])
" 2>/dev/null || echo "unknown")

    if [[ "$new_ip" != "unknown" ]]; then
        log "SUCCESS: New residential IP confirmed: $new_ip"
    else
        log "WARNING: Could not verify new IP (scraper may not be running)"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    log "=== Starting proxy session rotation ==="
    
    rotate_session
    restart_scraper
    verify_new_ip
    
    log "=== Proxy session rotation complete ==="
    log ""
}

main "$@"
