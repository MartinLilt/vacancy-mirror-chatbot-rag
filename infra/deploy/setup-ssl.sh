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

echo "==> Installing certbot on $SERVER"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SERVER" "
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
echo "==> Done. Now restart the stack:"
echo "    ssh -i $SSH_KEY $SERVER 'cd /etc/vacancy-mirror && docker compose up -d'"
