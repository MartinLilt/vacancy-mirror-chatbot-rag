#!/usr/bin/env bash
# Obtain Let's Encrypt TLS certificate for api.vacancy-mirror.com.
# Run once on the backend server after DNS A record is set.
#
# Usage:
#   bash infra/deploy/setup-ssl.sh
set -euo pipefail

DOMAIN="api.vacancy-mirror.com"
EMAIL="admin@vacancy-mirror.com"
SERVER="root@178.104.113.58"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/vacancy_mirror_deploy}"
SSH_PORT="${SSH_PORT:-2222}"

echo "==> Installing certbot on $SERVER"
ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "$SERVER" "
  apt-get install -y certbot
  systemctl stop nginx 2>/dev/null || true
  docker stop \$(docker ps -qf name=nginx) 2>/dev/null || true
  certbot certonly --standalone \
    --non-interactive --agree-tos \
    --email $EMAIL \
    -d $DOMAIN
  echo 'Certificate obtained OK'
  ls /etc/letsencrypt/live/$DOMAIN/
"

echo ""
echo "==> Setting up auto-renewal cron on $SERVER"
ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "$SERVER" "
  # Certbot auto-renewal: twice daily (recommended by Let's Encrypt).
  # --pre-hook / --post-hook stop/start nginx so certbot can bind :80.
  if ! crontab -l 2>/dev/null | grep -q 'certbot renew'; then
    (crontab -l 2>/dev/null; echo '0 3,15 * * * certbot renew --quiet --pre-hook \"systemctl stop nginx\" --post-hook \"systemctl start nginx\" >> /var/log/certbot-renew.log 2>&1') | crontab -
    echo 'Auto-renewal cron installed (03:00 and 15:00 daily)'
  else
    echo 'Auto-renewal cron already exists — skipping'
  fi
  echo ''
  crontab -l | grep certbot
"

echo ""
echo "==> Done. Now restart the stack:"
echo "    ssh -p $SSH_PORT -i $SSH_KEY $SERVER 'cd /etc/vacancy-mirror && docker compose up -d'"
