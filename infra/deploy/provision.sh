#!/usr/bin/env bash
# =============================================================================
# provision.sh — create two Hetzner servers and configure them
#
# Usage:
#   export HCLOUD_TOKEN=<your_token>
#   export GHCR_TOKEN=<github_personal_access_token>   # read:packages scope
#   export GHCR_USER=<github_username>
#   export DB_PASSWORD=<strong_password>
#   export OPENAI_API_KEY=<key>
#   export TELEGRAM_BOT_TOKEN=<token>
#   export OPENAI_MODEL=gpt-4.1-mini          # optional
#
#   bash infra/deploy/provision.sh
#
# What it does:
#   1. Creates SSH key pair (if not present) and uploads to Hetzner.
#   2. Creates server-backend  (CX22, Ubuntu 24.04):
#      - installs Docker, pulls postgres + backend images
#      - writes /etc/vacancy-mirror/backend.env
#      - starts postgres + backend via docker-compose
#   3. Creates server-scraper  (CX22, Ubuntu 24.04):
#      - installs Docker, pulls scraper image
#      - writes /etc/vacancy-mirror/scraper.env
#      - installs a daily cron job to run the scraper
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Config — edit these or override via env
# ---------------------------------------------------------------------------
HCLOUD_TOKEN="${HCLOUD_TOKEN:?HCLOUD_TOKEN is required}"
GHCR_TOKEN="${GHCR_TOKEN:?GHCR_TOKEN is required}"
GHCR_USER="${GHCR_USER:?GHCR_USER is required}"
DB_PASSWORD="${DB_PASSWORD:?DB_PASSWORD is required}"
OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4.1-mini}"

# Hetzner settings
SERVER_TYPE="cx23"            # 2 vCPU, 4 GB RAM, x86, nbg1
LOCATION="nbg1"               # Nuremberg (low latency to EU)
OS_IMAGE="ubuntu-24.04"
SSH_KEY_NAME="vacancy-mirror-deploy"
SSH_KEY_PATH="$HOME/.ssh/vacancy_mirror_deploy"

# Image names in ghcr.io
GHCR_BACKEND="ghcr.io/${GHCR_USER}/vacancy-mirror-backend:latest"
GHCR_SCRAPER="ghcr.io/${GHCR_USER}/vacancy-mirror-scraper:latest"

# Server names
BACKEND_SERVER="vacancy-mirror-backend"
SCRAPER_SERVER="vacancy-mirror-scraper"

# ---------------------------------------------------------------------------
# 0. Helpers
# ---------------------------------------------------------------------------
log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

check_deps() {
    for cmd in hcloud ssh ssh-keygen docker; do
        command -v "$cmd" >/dev/null 2>&1 \
            || die "'$cmd' not found. Install it first."
    done
}

# ---------------------------------------------------------------------------
# 1. SSH key
# ---------------------------------------------------------------------------
setup_ssh_key() {
    if [[ ! -f "$SSH_KEY_PATH" ]]; then
        log "Generating SSH key pair at $SSH_KEY_PATH ..."
        ssh-keygen -t ed25519 -C "vacancy-mirror-deploy" \
            -f "$SSH_KEY_PATH" -N ""
    fi

    # Upload to Hetzner if not already there
    if ! hcloud ssh-key list --output noheader \
            | awk '{print $2}' \
            | grep -qx "$SSH_KEY_NAME"; then
        log "Uploading SSH public key to Hetzner ..."
        hcloud ssh-key create \
            --name "$SSH_KEY_NAME" \
            --public-key-from-file "${SSH_KEY_PATH}.pub"
    else
        log "SSH key '$SSH_KEY_NAME' already on Hetzner."
    fi
}

# ---------------------------------------------------------------------------
# 2. Generic server helper
# ---------------------------------------------------------------------------
create_server_if_missing() {
    local name="$1"
    if hcloud server list --output noheader \
            | awk '{print $2}' \
            | grep -qx "$name"; then
        log "Server '$name' already exists — skipping creation."
        return
    fi

    log "Creating server '$name' ($SERVER_TYPE / $OS_IMAGE / $LOCATION) ..."
    hcloud server create \
        --name "$name" \
        --type "$SERVER_TYPE" \
        --image "$OS_IMAGE" \
        --location "$LOCATION" \
        --ssh-key "$SSH_KEY_NAME"
}

server_ip() {
    hcloud server describe "$1" \
        --output format="{{.PublicNet.IPv4.IP}}"
}

wait_for_ssh() {
    local ip="$1"
    log "Waiting for SSH on $ip ..."
    until ssh -o StrictHostKeyChecking=no \
               -o ConnectTimeout=5 \
               -i "$SSH_KEY_PATH" \
               "root@$ip" true 2>/dev/null; do
        sleep 5
    done
    log "SSH ready."
}

run_remote() {
    local ip="$1"; shift
    ssh -o StrictHostKeyChecking=no \
        -i "$SSH_KEY_PATH" \
        "root@$ip" "$@"
}

copy_file() {
    local ip="$1" src="$2" dst="$3"
    scp -o StrictHostKeyChecking=no \
        -i "$SSH_KEY_PATH" \
        "$src" "root@$ip:$dst"
}

# ---------------------------------------------------------------------------
# 3. Install Docker on a remote server
# ---------------------------------------------------------------------------
install_docker_remote() {
    local ip="$1"
    log "[$ip] Installing Docker ..."
    run_remote "$ip" bash <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
REMOTE
}

ensure_docker_forwarding_persistent() {
    local ip="$1"
    log "[$ip] Ensuring persistent Docker forwarding rules ..."
    run_remote "$ip" bash <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq iptables-persistent netfilter-persistent

# Keep host default FORWARD policy strict, but allow Docker bridge egress.
if ! iptables -C FORWARD -i docker0 -j ACCEPT 2>/dev/null; then
    iptables -I FORWARD 1 -i docker0 -j ACCEPT
fi
if ! iptables -C FORWARD -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I FORWARD 1 -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi

for bridge in $(ip -o link show | awk -F': ' '/: br-/{print $2}'); do
    if ! iptables -C FORWARD -i "$bridge" -j ACCEPT 2>/dev/null; then
        iptables -I FORWARD 1 -i "$bridge" -j ACCEPT
    fi
    if ! iptables -C FORWARD -o "$bridge" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
        iptables -I FORWARD 1 -o "$bridge" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    fi
done

netfilter-persistent save
systemctl enable netfilter-persistent >/dev/null 2>&1 || true
REMOTE
}

# ---------------------------------------------------------------------------
# 4. Backend server setup
# ---------------------------------------------------------------------------
setup_backend_server() {
    local ip
    ip=$(server_ip "$BACKEND_SERVER")
    log "--- Backend server: $ip ---"

    wait_for_ssh "$ip"
    install_docker_remote "$ip"
    ensure_docker_forwarding_persistent "$ip"

    log "[$ip] Logging into GHCR ..."
    run_remote "$ip" \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    log "[$ip] Creating /etc/vacancy-mirror/ ..."
    run_remote "$ip" "mkdir -p /etc/vacancy-mirror"

    log "[$ip] Writing backend.env ..."
    cat <<ENV | run_remote "$ip" "cat > /etc/vacancy-mirror/backend.env"
DB_PASSWORD=${DB_PASSWORD}
POSTGRES_PASSWORD=${DB_PASSWORD}
DB_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/vacancy_mirror
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
ENV

    log "[$ip] Copying docker-compose.backend.yml ..."
    # Substitute ${GHCR_USER} before copying — the env var won't be set on
    # the remote server, so we bake the image name into the compose file.
    local tmp_compose
    tmp_compose=$(mktemp)
    sed "s|\${GHCR_USER}|${GHCR_USER}|g" \
        "infra/deploy/docker-compose.backend.yml" > "$tmp_compose"
    copy_file "$ip" "$tmp_compose" "/etc/vacancy-mirror/docker-compose.yml"
    rm -f "$tmp_compose"

    log "[$ip] Copying DB init SQL ..."
    run_remote "$ip" "mkdir -p /etc/vacancy-mirror/db"
    copy_file "$ip" \
        "infra/db/init.sql" \
        "/etc/vacancy-mirror/db/init.sql"

    log "[$ip] Pulling images and starting backend stack ..."
    run_remote "$ip" bash <<REMOTE
set -euo pipefail
cd /etc/vacancy-mirror
docker compose pull
docker compose up -d
REMOTE

    log "Backend stack is up on $ip."
    log "Postgres port 5432 is NOT exposed to the public — internal only."
}

# ---------------------------------------------------------------------------
# 5. Scraper server setup
# ---------------------------------------------------------------------------
setup_scraper_server() {
    local backend_ip scraper_ip
    backend_ip=$(server_ip "$BACKEND_SERVER")
    scraper_ip=$(server_ip "$SCRAPER_SERVER")
    log "--- Scraper server: $scraper_ip ---"

    wait_for_ssh "$scraper_ip"
    install_docker_remote "$scraper_ip"
    ensure_docker_forwarding_persistent "$scraper_ip"

    log "[$scraper_ip] Logging into GHCR ..."
    run_remote "$scraper_ip" \
        "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"

    log "[$scraper_ip] Creating /etc/vacancy-mirror/ ..."
    run_remote "$scraper_ip" "mkdir -p /etc/vacancy-mirror"

    log "[$scraper_ip] Writing scraper.env ..."
    cat <<ENV | run_remote "$scraper_ip" "cat > /etc/vacancy-mirror/scraper.env"
DB_URL=postgresql://app:${DB_PASSWORD}@${backend_ip}:5432/vacancy_mirror
CHROME_PATH=/usr/bin/chromium
LOG_LEVEL=INFO
ENV

    log "[$scraper_ip] Writing scraper run script ..."
    run_remote "$scraper_ip" bash <<'REMOTE'
cat > /usr/local/bin/run-scraper.sh << 'SCRIPT'
#!/usr/bin/env bash
# Pull latest scraper image and run it.
set -euo pipefail
IMAGE="GHCR_SCRAPER_PLACEHOLDER"
ENV_FILE="/etc/vacancy-mirror/scraper.env"

docker pull "$IMAGE"
docker run --rm \
    --env-file "$ENV_FILE" \
    --shm-size=1g \
    "$IMAGE" \
    python -m scraper.cli scrape \
        --uid "${CATEGORY_UID:-531770282580668418}" \
        --max-pages "${MAX_PAGES:-100}"
SCRIPT
chmod +x /usr/local/bin/run-scraper.sh
REMOTE

    # Substitute real image name
    run_remote "$scraper_ip" \
        "sed -i 's|GHCR_SCRAPER_PLACEHOLDER|${GHCR_SCRAPER}|g' \
        /usr/local/bin/run-scraper.sh"

    log "[$scraper_ip] Installing daily cron job (03:00 UTC) ..."
    run_remote "$scraper_ip" \
        "echo '0 3 * * * root /usr/local/bin/run-scraper.sh >> /var/log/scraper.log 2>&1' \
        > /etc/cron.d/vacancy-mirror-scraper && chmod 644 /etc/cron.d/vacancy-mirror-scraper"

    log "Scraper server configured. Cron runs daily at 03:00 UTC."
    log "Manual run: ssh -i $SSH_KEY_PATH root@$scraper_ip /usr/local/bin/run-scraper.sh"
}

# ---------------------------------------------------------------------------
# 6. Open postgres port on backend server firewall FOR scraper server only
# ---------------------------------------------------------------------------
open_postgres_for_scraper() {
    local backend_ip scraper_ip
    backend_ip=$(server_ip "$BACKEND_SERVER")
    scraper_ip=$(server_ip "$SCRAPER_SERVER")

    # Allow scraper -> postgres (5432). Prefer ufw when available,
    # otherwise use iptables directly.
    log "Allowing $scraper_ip to reach postgres on backend ..."
    run_remote "$backend_ip" bash <<REMOTE
set -euo pipefail
if command -v ufw >/dev/null 2>&1; then
    ufw allow from ${scraper_ip} to any port 5432 proto tcp
    ufw --force enable
else
    if ! iptables -C INPUT -p tcp -s ${scraper_ip} --dport 5432 -j ACCEPT 2>/dev/null; then
        iptables -I INPUT 1 -p tcp -s ${scraper_ip} --dport 5432 -j ACCEPT
    fi
    if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save
    fi
fi
REMOTE
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    check_deps

    log "=== Hetzner provisioning started ==="

    setup_ssh_key

    create_server_if_missing "$BACKEND_SERVER"
    create_server_if_missing "$SCRAPER_SERVER"

    setup_backend_server
    setup_scraper_server
    open_postgres_for_scraper

    local backend_ip scraper_ip
    backend_ip=$(server_ip "$BACKEND_SERVER")
    scraper_ip=$(server_ip "$SCRAPER_SERVER")

    log ""
    log "=== DONE ==="
    log "  Backend  : $backend_ip"
    log "  Scraper  : $scraper_ip"
    log ""
    log "  SSH backend : ssh -i $SSH_KEY_PATH root@$backend_ip"
    log "  SSH scraper : ssh -i $SSH_KEY_PATH root@$scraper_ip"
    log ""
    log "  Logs backend : ssh root@$backend_ip docker compose logs -f"
    log "  Logs scraper : ssh root@$scraper_ip tail -f /var/log/scraper.log"
}

main "$@"
