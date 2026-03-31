#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vacancy-mirror/.env"
SESSION_ID="upwork-$(date +%Y%m%d-%H%M%S)"

# Update PROXY_URL with new session ID
# Pattern for Webshare: session-XXXXX:password
sed -i "s/session-[^:]*/session-${SESSION_ID}/" "$ENV_FILE"

echo "[$(date)] Rotated Webshare session to: ${SESSION_ID}"
