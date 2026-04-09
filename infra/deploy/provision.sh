#!/usr/bin/env bash
# =============================================================================
# provision.sh — create two Hetzner servers, harden, deploy everything
#
# Usage:
#   source .env   # or export vars manually
#   bash infra/deploy/provision.sh
#
# Requires: hcloud CLI, ssh, scp
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Load .env
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport; source "$REPO_ROOT/.env"; set +o allexport
fi

# ---------------------------------------------------------------------------
# Required env
# ---------------------------------------------------------------------------
HCLOUD_TOKEN="${HCLOUD_TOKEN:?Set HCLOUD_TOKEN}"
GHCR_TOKEN="${GHCR_TOKEN:?Set GHCR_TOKEN}"
GHCR_USER="${GHCR_USER:?Set GHCR_USER}"
DB_PASSWORD="${DB_PASSWORD:?Set DB_PASSWORD}"
OPENAI_API_KEY="${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN}"

# Optional env (with defaults)
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4.1-mini}"
GRAFANA_BACKEND_PASSWORD="${GRAFANA_BACKEND_PASSWORD:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
SUPPORT_API_TOKEN="${SUPPORT_API_TOKEN:-}"
SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASSWORD="${SMTP_PASSWORD:-}"
SMTP_TLS="${SMTP_TLS:-true}"
SUPPORT_FROM_EMAIL="${SUPPORT_FROM_EMAIL:-support@vacancy-mirror.com}"
CHATWOOT_BASE_URL="${CHATWOOT_BASE_URL:-}"
CHATWOOT_ACCOUNT_ID="${CHATWOOT_ACCOUNT_ID:-}"
CHATWOOT_INBOX_ID="${CHATWOOT_INBOX_ID:-}"
CHATWOOT_API_ACCESS_TOKEN="${CHATWOOT_API_ACCESS_TOKEN:-}"
CHATWOOT_WEBHOOK_TOKEN="${CHATWOOT_WEBHOOK_TOKEN:-}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-}"
SCRAPER_API_KEY="${SCRAPER_API_KEY:-}"
PROXY_URL="${PROXY_URL:-}"
WEBSHARE_API_KEY="${WEBSHARE_API_KEY:-}"
FLARESOLVERR_PROXY_URL="${FLARESOLVERR_PROXY_URL:-}"
GOOGLE_SHEETS_ID="${GOOGLE_SHEETS_ID:-}"
START_PREVIEW_VIDEO_ENABLED="${START_PREVIEW_VIDEO_ENABLED:-1}"
START_PREVIEW_VIDEO_PATH="${START_PREVIEW_VIDEO_PATH:-}"

# Hetzner settings
SERVER_TYPE="cx23"
LOCATION="nbg1"
OS_IMAGE="ubuntu-24.04"
SSH_KEY_NAME="vacancy-mirror-deploy"
SSH_KEY_PATH="$HOME/.ssh/vacancy_mirror_deploy"
NEW_SSH_PORT=2222

BACKEND_SERVER="vacancy-mirror-backend"
SCRAPER_SERVER="vacancy-mirror-scraper"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

for cmd in hcloud ssh scp; do
    command -v "$cmd" >/dev/null || die "'$cmd' not found"
done

server_ip() {
    hcloud server describe "$1" --output format="{{.PublicNet.IPv4.IP}}"
}

run22() {
    local ip="$1"; shift
    ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
        -p 22 -i "$SSH_KEY_PATH" "root@$ip" "$@"
}

run2222() {
    local ip="$1"; shift
    ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
        -p "$NEW_SSH_PORT" -i "$SSH_KEY_PATH" "root@$ip" "$@"
}

copy2222() {
    local ip="$1" src="$2" dst="$3"
    scp -o StrictHostKeyChecking=accept-new -P "$NEW_SSH_PORT" -i "$SSH_KEY_PATH" "$src" "root@$ip:$dst"
}

copydir2222() {
    local ip="$1" src="$2" dst="$3"
    scp -r -o StrictHostKeyChecking=accept-new -P "$NEW_SSH_PORT" -i "$SSH_KEY_PATH" "$src/." "root@$ip:$dst"
}

wait_for_ssh() {
    local ip="$1" port="${2:-22}"
    log "Waiting for SSH on $ip:$port ..."
    for i in $(seq 1 60); do
        ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
            -p "$port" -i "$SSH_KEY_PATH" "root@$ip" true 2>/dev/null && return 0
        sleep 5
    done
    die "SSH on $ip:$port not ready after 5 minutes"
}

# ---------------------------------------------------------------------------
# 1. SSH key
# ---------------------------------------------------------------------------
setup_ssh_key() {
    if [[ ! -f "$SSH_KEY_PATH" ]]; then
        log "Generating SSH key pair..."
        ssh-keygen -t ed25519 -C "vacancy-mirror-deploy" -f "$SSH_KEY_PATH" -N ""
    fi
    if ! hcloud ssh-key list --output noheader | awk '{print $2}' | grep -qx "$SSH_KEY_NAME"; then
        log "Uploading SSH key to Hetzner..."
        hcloud ssh-key create --name "$SSH_KEY_NAME" --public-key-from-file "${SSH_KEY_PATH}.pub"
    else
        log "SSH key already on Hetzner."
    fi
}

# ---------------------------------------------------------------------------
# 2. Create servers
# ---------------------------------------------------------------------------
create_server() {
    local name="$1"
    if hcloud server list --output noheader | awk '{print $2}' | grep -qx "$name"; then
        log "Server '$name' already exists."
        return
    fi
    log "Creating server '$name' ($SERVER_TYPE / $OS_IMAGE / $LOCATION)..."
    hcloud server create \
        --name "$name" \
        --type "$SERVER_TYPE" \
        --image "$OS_IMAGE" \
        --location "$LOCATION" \
        --ssh-key "$SSH_KEY_NAME"
}

# ---------------------------------------------------------------------------
# 3. Hardening (runs on fresh server with port 22)
# ---------------------------------------------------------------------------
harden_server() {
    local ip="$1" name="$2" extra_ufw="${3:-}"
    log "===== Hardening $name ($ip) ====="

    run22 "$ip" bash <<REMOTE
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "--- SSH hardening ---"
sed -i 's/^#*Port .*/Port ${NEW_SSH_PORT}/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
grep -q '^MaxAuthTries' /etc/ssh/sshd_config && \
    sed -i 's/^MaxAuthTries .*/MaxAuthTries 3/' /etc/ssh/sshd_config || \
    echo 'MaxAuthTries 3' >> /etc/ssh/sshd_config
sed -i 's/^#*X11Forwarding .*/X11Forwarding no/' /etc/ssh/sshd_config

echo "--- UFW firewall ---"
apt-get update -qq
apt-get install -y -qq ufw
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow ${NEW_SSH_PORT}/tcp comment 'SSH'
${extra_ufw}
echo "y" | ufw enable

echo "--- fail2ban ---"
apt-get install -y -qq fail2ban
cat > /etc/fail2ban/jail.local <<'F2B'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
backend  = systemd

[sshd]
enabled  = true
port     = SSHPORT_PLACEHOLDER
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 7200
F2B
sed -i "s/SSHPORT_PLACEHOLDER/${NEW_SSH_PORT}/" /etc/fail2ban/jail.local
systemctl enable fail2ban
systemctl restart fail2ban

echo "--- Auto security updates ---"
apt-get install -y -qq unattended-upgrades apt-listchanges
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT

echo "--- auditd ---"
apt-get install -y -qq auditd
cat > /etc/audit/rules.d/hardening.rules <<'AUDIT'
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/ssh/sshd_config -p wa -k sshd_config
-w /etc/vacancy-mirror/ -p wa -k vacancy_mirror_config
-w /etc/crontab -p wa -k cron
-w /etc/cron.d/ -p wa -k cron
-w /etc/cron.hourly/ -p wa -k cron
-w /var/spool/cron/ -p wa -k cron
-w /usr/bin/docker -p x -k docker_commands
AUDIT
systemctl enable auditd
systemctl restart auditd

echo "--- Secure journal ---"
sed -i 's/^#*SystemMaxUse=.*/SystemMaxUse=500M/' /etc/systemd/journald.conf
systemctl restart systemd-journald

echo "--- Restart SSH on port ${NEW_SSH_PORT} ---"
systemctl restart sshd || systemctl restart ssh
echo "✅ Hardening complete"
REMOTE

    sleep 3
    log "Testing SSH on port ${NEW_SSH_PORT}..."
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
        -i "$SSH_KEY_PATH" -p "${NEW_SSH_PORT}" "root@$ip" "echo OK" 2>/dev/null; then
        log "✅ SSH OK on port ${NEW_SSH_PORT} for $name"
    else
        die "SSH on port ${NEW_SSH_PORT} FAILED for $name"
    fi
}

# ---------------------------------------------------------------------------
# 4. Install Docker (port 2222)
# ---------------------------------------------------------------------------
install_docker() {
    local ip="$1"
    log "[$ip] Installing Docker..."
    run2222 "$ip" bash <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

apt-get install -y -qq iptables-persistent netfilter-persistent
iptables -I FORWARD 1 -i docker0 -j ACCEPT 2>/dev/null || true
iptables -I FORWARD 1 -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
iptables -I FORWARD 1 -i br+ -j ACCEPT 2>/dev/null || true
iptables -I FORWARD 1 -o br+ -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
netfilter-persistent save
echo "✅ Docker installed"
REMOTE
}

# ---------------------------------------------------------------------------
# 5. Deploy BACKEND
# ---------------------------------------------------------------------------
deploy_backend() {
    local ip="$1"
    log "===== Deploying backend on $ip ====="

    run2222 "$ip" "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    log "Creating directories..."
    run2222 "$ip" "mkdir -p /etc/vacancy-mirror/db /etc/vacancy-mirror/grafana-backend/provisioning /etc/vacancy-mirror/secrets /etc/vacancy-mirror/chatwoot /etc/vacancy-mirror/assets"

    log "Writing backend.env..."
    cat <<ENV | run2222 "$ip" "cat > /etc/vacancy-mirror/backend.env"
DB_PASSWORD=${DB_PASSWORD}
POSTGRES_PASSWORD=${DB_PASSWORD}
DB_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/vacancy_mirror
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_DROP_PENDING_UPDATES=true
GOOGLE_SHEETS_ID=${GOOGLE_SHEETS_ID}
GOOGLE_SERVICE_ACCOUNT_JSON=/etc/vacancy-mirror/secrets/google_service_account.json
SUPPORT_API_TOKEN=${SUPPORT_API_TOKEN}
SUPPORT_FROM_EMAIL=${SUPPORT_FROM_EMAIL}
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_TLS=${SMTP_TLS}
CHATWOOT_BASE_URL=${CHATWOOT_BASE_URL}
CHATWOOT_ACCOUNT_ID=${CHATWOOT_ACCOUNT_ID}
CHATWOOT_INBOX_ID=${CHATWOOT_INBOX_ID}
CHATWOOT_API_ACCESS_TOKEN=${CHATWOOT_API_ACCESS_TOKEN}
CHATWOOT_WEBHOOK_TOKEN=${CHATWOOT_WEBHOOK_TOKEN}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
START_PREVIEW_VIDEO_ENABLED=${START_PREVIEW_VIDEO_ENABLED}
START_PREVIEW_VIDEO_PATH=${START_PREVIEW_VIDEO_PATH}
GRAFANA_BACKEND_PASSWORD=${GRAFANA_BACKEND_PASSWORD}
GRAFANA_BACKEND_ROOT_URL=http://localhost:3001
ASSISTANT_INFER_URLS=http://assistant-infer-1:8090,http://assistant-infer-2:8090,http://assistant-infer-3:8090
WEBHOOK_PORT=8080
ENV

    log "Copying compose, nginx, init.sql, grafana provisioning..."
    local tmp_compose; tmp_compose=$(mktemp)
    sed "s|\${GHCR_USER}|${GHCR_USER}|g" "$REPO_ROOT/infra/deploy/docker-compose.backend.yml" > "$tmp_compose"
    copy2222 "$ip" "$tmp_compose" "/etc/vacancy-mirror/docker-compose.yml"
    rm -f "$tmp_compose"
    copy2222 "$ip" "$REPO_ROOT/infra/deploy/nginx.conf" "/etc/vacancy-mirror/nginx.conf"
    copy2222 "$ip" "$REPO_ROOT/infra/db/init.sql" "/etc/vacancy-mirror/db/init.sql"
    copydir2222 "$ip" "$REPO_ROOT/infra/monitoring/grafana-backend/provisioning" "/etc/vacancy-mirror/grafana-backend/provisioning"

    if [[ -f "$REPO_ROOT/secrets/google_service_account.json" ]]; then
        copy2222 "$ip" "$REPO_ROOT/secrets/google_service_account.json" "/etc/vacancy-mirror/secrets/google_service_account.json"
    fi

    if [[ -f "$REPO_ROOT/backend/src/backend/assets/send_video.mp4" ]]; then
        copy2222 "$ip" "$REPO_ROOT/backend/src/backend/assets/send_video.mp4" "/etc/vacancy-mirror/assets/send_video.mp4"
    fi

    log "Installing nginx on host..."
    run2222 "$ip" bash <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq nginx
cp /etc/vacancy-mirror/nginx.conf /etc/nginx/nginx.conf
nginx -t && systemctl enable nginx && systemctl restart nginx
REMOTE

    log "Securing env files..."
    run2222 "$ip" "chmod 600 /etc/vacancy-mirror/*.env; chmod 700 /etc/vacancy-mirror/"

    log "Pulling images & starting backend stack..."
    run2222 "$ip" bash <<'REMOTE'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull
docker compose up -d
echo "✅ Backend stack running"
docker compose ps
REMOTE

    log "✅ Backend deployed on $ip"
}

# ---------------------------------------------------------------------------
# 6. Deploy SCRAPER
# ---------------------------------------------------------------------------
deploy_scraper() {
    local ip="$1"
    log "===== Deploying scraper on $ip ====="

    run2222 "$ip" "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    log "Creating directories..."
    run2222 "$ip" "mkdir -p /etc/vacancy-mirror/db /etc/vacancy-mirror/grafana/provisioning"

    log "Writing scraper .env..."
    cat <<ENV | run2222 "$ip" "cat > /etc/vacancy-mirror/.env"
DB_PASSWORD=${DB_PASSWORD}
SCRAPER_API_KEY=${SCRAPER_API_KEY}
PROXY_URL=${PROXY_URL}
WEBSHARE_API_KEY=${WEBSHARE_API_KEY}
FLARESOLVERR_PROXY_URL=${FLARESOLVERR_PROXY_URL}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
GRAFANA_ROOT_URL=http://localhost:3000
ENV

    log "Copying compose, init.sql, prometheus, grafana provisioning..."
    copy2222 "$ip" "$REPO_ROOT/infra/deploy/docker-compose.server2.yml" "/etc/vacancy-mirror/docker-compose.yml"
    copy2222 "$ip" "$REPO_ROOT/infra/db/init.sql" "/etc/vacancy-mirror/db/init.sql"
    copy2222 "$ip" "$REPO_ROOT/infra/monitoring/prometheus.yml" "/etc/vacancy-mirror/prometheus.yml"
    copydir2222 "$ip" "$REPO_ROOT/infra/monitoring/grafana/provisioning" "/etc/vacancy-mirror/grafana/provisioning"

    log "Securing env files..."
    run2222 "$ip" "chmod 600 /etc/vacancy-mirror/.env; chmod 700 /etc/vacancy-mirror/"

    log "Pulling images & starting scraper stack..."
    run2222 "$ip" bash <<'REMOTE'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull
docker compose up -d
echo "✅ Scraper stack running"
docker compose ps
REMOTE

    log "✅ Scraper deployed on $ip"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "=== PROVISION START ==="

    setup_ssh_key

    log "--- Creating servers ---"
    create_server "$BACKEND_SERVER"
    create_server "$SCRAPER_SERVER"

    local backend_ip scraper_ip
    backend_ip=$(server_ip "$BACKEND_SERVER")
    scraper_ip=$(server_ip "$SCRAPER_SERVER")

    log "Backend IP:  $backend_ip"
    log "Scraper IP:  $scraper_ip"

    wait_for_ssh "$backend_ip" 22
    wait_for_ssh "$scraper_ip" 22

    harden_server "$backend_ip" "backend" \
        "ufw allow 80/tcp comment 'HTTP nginx'; ufw allow 443/tcp comment 'HTTPS nginx'"
    harden_server "$scraper_ip" "scraper" ""

    install_docker "$backend_ip"
    install_docker "$scraper_ip"

    deploy_backend "$backend_ip"
    deploy_scraper "$scraper_ip"

    # Save new IPs to .env
    log "Updating .env with new server IPs..."
    if grep -q '^BACKEND_SERVER_IP=' "$REPO_ROOT/.env" 2>/dev/null; then
        sed -i.bak "s/^BACKEND_SERVER_IP=.*/BACKEND_SERVER_IP=$backend_ip/" "$REPO_ROOT/.env"
        sed -i.bak "s/^SCRAPER_SERVER_IP=.*/SCRAPER_SERVER_IP=$scraper_ip/" "$REPO_ROOT/.env"
    else
        printf '\n# Server IPs\nBACKEND_SERVER_IP=%s\nSCRAPER_SERVER_IP=%s\n' \
            "$backend_ip" "$scraper_ip" >> "$REPO_ROOT/.env"
    fi

    ssh-keygen -R "$backend_ip" 2>/dev/null || true
    ssh-keygen -R "$scraper_ip" 2>/dev/null || true

    log ""
    log "=========================================="
    log "  ✅ PROVISION COMPLETE"
    log "=========================================="
    log ""
    log "  Backend:  $backend_ip"
    log "  Scraper:  $scraper_ip"
    log ""
    log "  SSH:"
    log "    ssh -i $SSH_KEY_PATH -p ${NEW_SSH_PORT} root@$backend_ip"
    log "    ssh -i $SSH_KEY_PATH -p ${NEW_SSH_PORT} root@$scraper_ip"
    log ""
    log "  Grafana backend:  ssh -N -L 3001:127.0.0.1:3001 -p ${NEW_SSH_PORT} -i $SSH_KEY_PATH root@$backend_ip"
    log "  Grafana scraper:  ssh -N -L 3000:127.0.0.1:3000 -p ${NEW_SSH_PORT} -i $SSH_KEY_PATH root@$scraper_ip"
}

main "$@"
