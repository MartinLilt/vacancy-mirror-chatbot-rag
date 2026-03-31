#!/bin/bash
# ---------------------------------------------------------------------------
# Rotate Webshare.io proxy session every 30 minutes
#
# Purpose:
#   - Webshare sticky sessions last max 30 minutes
#   - Rotate before expiry to maintain consistent IP during scraping
#   - Prevents mid-scrape IP changes that trigger Cloudflare
#
# Usage:
#   1. Make executable: chmod +x rotate_proxy_session_webshare.sh
#   2. Test manually: ./rotate_proxy_session_webshare.sh
#   3. Add to crontab: */30 * * * * /path/to/rotate_proxy_session_webshare.sh
#
# Schedule:
#   Runs every 30 minutes (before Webshare session expires)
#
# What it does:
#   - Generates new session ID: upwork-HHMMSS (timestamp)
#   - Updates PROXY_URL in .env file
#   - Does NOT restart scraper (cookies persist across rotations)
#
# Example:
#   Before: session-upwork-120000
#   After:  session-upwork-123000
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

    # Generate new session ID (timestamp-based for uniqueness)
    new_session="upwork-$(date +%Y%m%d-%H%M%S)"
    log "INFO: Generating new session ID: $new_session"

    # Replace session ID in .env file
    # Pattern for Webshare: session-XXXXX (between 'session-' and ':')
    # Example: session-upwork123:password → session-upwork-20260331-120000:password
    sed -i.bak "s/session-[^:]*:/session-$new_session:/" "$ENV_FILE"

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

verify_new_ip() {
    log "INFO: Waiting 5s for session to initialize..."
    sleep 5

    log "INFO: Verifying new IP address..."
    
    # Extract proxy URL from .env
    proxy_url=$(grep "^PROXY_URL=" "$ENV_FILE" | cut -d'=' -f2)
    
    # Check IP via proxy (simple curl test)
    new_ip=$(curl -x "$proxy_url" -s https://api.ipify.org 2>/dev/null || echo "unknown")

    if [[ "$new_ip" != "unknown" ]]; then
        log "SUCCESS: New residential IP confirmed: $new_ip"
    else
        log "WARNING: Could not verify new IP (proxy may need warmup)"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    log "=== Starting Webshare proxy session rotation ==="
    
    rotate_session
    verify_new_ip
    
    log "=== Proxy session rotation complete (scraper NOT restarted) ==="
    log ""
}

main "$@"
