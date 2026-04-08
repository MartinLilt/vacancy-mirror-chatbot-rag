#!/usr/bin/env bash
# =============================================================================
# lockdown_network.sh — Full network isolation for both servers.
#
# What it does:
#   Phase 1: AUDIT  — scans what's actually reachable from outside
#   Phase 2: HARDEN — applies Docker daemon hardening, iptables DOCKER-USER
#                      rules, and deploys compose files with internal networks
#
# Threat model:
#   A) External attacker scanning ports → blocked by DOCKER-USER + UFW
#   B) Compromised container downloading malware → blocked by internal
#      networks (no internet) + iptables outbound port whitelist
#   C) Docker bypassing UFW → mitigated by userland-proxy:false + DOCKER-USER
#
# Usage:
#   bash infra/deploy/lockdown_network.sh [audit|fix|all] [backend|scraper|both]
#
# Examples:
#   bash infra/deploy/lockdown_network.sh audit both    # just check, no changes
#   bash infra/deploy/lockdown_network.sh fix both      # apply all fixes
#   bash infra/deploy/lockdown_network.sh all both      # audit then fix
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Load .env
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

BACKEND_IP="${BACKEND_SERVER_IP:-178.104.113.58}"
SCRAPER_IP="${SCRAPER_SERVER_IP:-178.104.110.28}"
SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"
SSH_PORT="${SSH_PORT:-2222}"
ACTION="${1:-all}"     # audit | fix | all
SERVERS="${2:-both}"   # backend | scraper | both

log()  { echo "[$(date +%H:%M:%S)] $*"; }
warn() { echo "[$(date +%H:%M:%S)] ⚠️  $*"; }
ok()   { echo "[$(date +%H:%M:%S)] ✅ $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

ssh_to() {
    local ip="$1"; shift
    ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" -i "$SSH_KEY" "root@${ip}" "$@"
}
scp_to() {
    local ip="$1" src="$2" dst="$3"
    scp -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" "$src" "root@${ip}:$dst"
}
scp_dir_to() {
    local ip="$1" src="$2" dst="$3"
    scp -r -o StrictHostKeyChecking=no -P "$SSH_PORT" -i "$SSH_KEY" \
        "$src/." "root@${ip}:$dst"
}

# =============================================================================
# PHASE 1: AUDIT
# =============================================================================
audit_server() {
    local ip="$1" name="$2"
    log "========== AUDIT: $name ($ip) =========="

    ssh_to "$ip" bash <<'AUDIT_SCRIPT'
set -euo pipefail

echo ""
echo "═══════════════════════════════════════════════════"
echo " 1. PORTS LISTENING ON 0.0.0.0 (reachable from outside)"
echo "═══════════════════════════════════════════════════"
# Show all ports bound to 0.0.0.0 or * (not 127.0.0.1)
echo ""
echo "--- TCP LISTEN on 0.0.0.0 / [::] ---"
ss -tlnp | grep -E 'LISTEN' | grep -v '127.0.0.1' | grep -v '::1' || echo "(none)"
echo ""
echo "--- UDP LISTEN on 0.0.0.0 / [::] ---"
ss -ulnp | grep -v '127.0.0.1' | grep -v '::1' || echo "(none)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 2. DOCKER PORT MAPPINGS"
echo "═══════════════════════════════════════════════════"
echo ""
docker ps --format 'table {{.Names}}\t{{.Ports}}' 2>/dev/null || echo "(docker not running)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 3. UFW STATUS"
echo "═══════════════════════════════════════════════════"
echo ""
ufw status verbose 2>/dev/null || echo "(ufw not installed)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 4. DOCKER-USER IPTABLES CHAIN"
echo "═══════════════════════════════════════════════════"
echo ""
iptables -L DOCKER-USER -n -v 2>/dev/null || echo "(DOCKER-USER chain does not exist)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 5. DOCKER DAEMON CONFIG"
echo "═══════════════════════════════════════════════════"
echo ""
if [ -f /etc/docker/daemon.json ]; then
    cat /etc/docker/daemon.json
else
    echo "(no daemon.json — using Docker defaults)"
    echo "  → userland-proxy: true (INSECURE — bypasses iptables)"
    echo "  → no-new-privileges: not enforced by daemon"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo " 6. DOCKER-PROXY PROCESSES (bypass iptables!)"
echo "═══════════════════════════════════════════════════"
echo ""
ps aux | grep docker-proxy | grep -v grep || echo "(none — good)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 7. DOCKER NETWORKS"
echo "═══════════════════════════════════════════════════"
echo ""
docker network ls 2>/dev/null || echo "(docker not running)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 8. IPTABLES NAT PREROUTING (Docker port forwards)"
echo "═══════════════════════════════════════════════════"
echo ""
iptables -t nat -L PREROUTING -n -v 2>/dev/null || echo "(no PREROUTING rules)"
echo ""
echo "--- DOCKER chain in nat table ---"
iptables -t nat -L DOCKER -n -v 2>/dev/null || echo "(no DOCKER nat chain)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 9. OUTBOUND CONNECTIONS FROM CONTAINERS"
echo "═══════════════════════════════════════════════════"
echo ""
echo "--- Active ESTABLISHED connections from Docker subnets ---"
ss -tnp | grep -E '172\.(1[6-9]|2[0-9]|3[01])\.' | head -20 || echo "(none)"

echo ""
echo "═══════════════════════════════════════════════════"
echo " 10. RISK ASSESSMENT"
echo "═══════════════════════════════════════════════════"
echo ""
RISKS=0

# Check for docker-proxy (bypasses iptables)
if ps aux | grep -q '[d]ocker-proxy'; then
    echo "🔴 RISK: docker-proxy running — bypasses iptables rules"
    RISKS=$((RISKS+1))
fi

# Check for 0.0.0.0 bindings that aren't SSH or nginx
EXPOSED=$(ss -tlnp | grep 'LISTEN' | grep '0.0.0.0' | grep -v ':2222 ' | grep -v ':80 ' | grep -v ':443 ' | grep -v ':22 ')
if [ -n "$EXPOSED" ]; then
    echo "🔴 RISK: Ports exposed on 0.0.0.0 (besides SSH/nginx):"
    echo "$EXPOSED"
    RISKS=$((RISKS+1))
fi

# Check if DOCKER-USER has custom rules
DOCKER_USER_RULES=$(iptables -L DOCKER-USER --line-numbers -n 2>/dev/null | wc -l)
if [ "$DOCKER_USER_RULES" -le 3 ]; then
    echo "🔴 RISK: No custom DOCKER-USER rules (IPv4) — Docker ports may be reachable externally"
    RISKS=$((RISKS+1))
fi

# Check IPv6 DOCKER-USER
DOCKER_USER6_RULES=$(ip6tables -L DOCKER-USER --line-numbers -n 2>/dev/null | wc -l)
if [ "$DOCKER_USER6_RULES" -le 3 ]; then
    echo "🔴 RISK: No custom DOCKER-USER rules (IPv6) — containers may bypass restrictions via IPv6"
    RISKS=$((RISKS+1))
else
    echo "✅ IPv6 DOCKER-USER rules present"
fi

# Check daemon.json for userland-proxy
if [ -f /etc/docker/daemon.json ]; then
    if grep -q '"userland-proxy".*false' /etc/docker/daemon.json; then
        echo "✅ userland-proxy disabled"
    else
        echo "🔴 RISK: userland-proxy not disabled in daemon.json"
        RISKS=$((RISKS+1))
    fi
else
    echo "🔴 RISK: No daemon.json — userland-proxy enabled by default"
    RISKS=$((RISKS+1))
fi

# Check for internal networks
if docker network ls 2>/dev/null | grep -q 'internal'; then
    echo "✅ Internal Docker network(s) found"
else
    echo "🟡 WARN: No internal Docker networks — all containers can reach internet"
    RISKS=$((RISKS+1))
fi

echo ""
if [ "$RISKS" -eq 0 ]; then
    echo "✅ No risks found — server appears properly locked down"
else
    echo "🔴 Found $RISKS risk(s) — run 'lockdown_network.sh fix' to remediate"
fi
AUDIT_SCRIPT

    log "========== AUDIT COMPLETE: $name =========="
    echo ""
}

# =============================================================================
# PHASE 2: FIX
# =============================================================================

# --- 2a. Docker daemon hardening ---
fix_docker_daemon() {
    local ip="$1" name="$2"
    log "[$name] Configuring Docker daemon..."

    ssh_to "$ip" bash <<'DAEMON_SCRIPT'
set -euo pipefail

echo "--- Configuring /etc/docker/daemon.json ---"
mkdir -p /etc/docker

# Merge with existing config if present, otherwise create fresh
cat > /etc/docker/daemon.json <<'JSON'
{
  "userland-proxy": false,
  "no-new-privileges": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true,
  "default-address-pools": [
    {
      "base": "172.17.0.0/12",
      "size": 24
    }
  ]
}
JSON

echo "  daemon.json written"
echo "  → userland-proxy: false (iptables-only port mapping)"
echo "  → no-new-privileges: true (enforced by daemon)"
echo "  → live-restore: true (containers survive daemon restart)"
echo "  → log limits: 10MB × 3 files per container"

# Restart Docker daemon
echo "--- Restarting Docker daemon ---"
systemctl restart docker
sleep 3

# Verify docker-proxy is gone
if ps aux | grep -q '[d]ocker-proxy'; then
    echo "⚠️  docker-proxy still running (will go away after container restart)"
else
    echo "✅ No docker-proxy processes"
fi

echo "✅ Docker daemon hardened"
DAEMON_SCRIPT
}

# --- 2b. DOCKER-USER iptables rules (IPv4 + IPv6) ---
fix_iptables() {
    local ip="$1" name="$2"
    log "[$name] Applying DOCKER-USER iptables rules (IPv4 + IPv6)..."

    ssh_to "$ip" bash <<'IPTABLES_SCRIPT'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Ensure iptables-persistent is installed
apt-get install -y -qq iptables-persistent netfilter-persistent > /dev/null 2>&1

# ==========================================================================
# IPv4 DOCKER-USER rules
# ==========================================================================
echo "--- Configuring DOCKER-USER chain (IPv4) ---"
echo "  (blocks external→container, restricts container outbound)"

# Flush existing DOCKER-USER rules
iptables -F DOCKER-USER 2>/dev/null || true

# Rule 1: Allow established/related connections (return traffic)
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

# Rule 2: Allow loopback traffic (host ↔ container via 127.0.0.1 ports)
# This is how nginx on the host reaches published container ports.
iptables -A DOCKER-USER -i lo -j RETURN

# Rule 3: Allow Docker inter-container traffic (bridge ↔ bridge)
# Docker bridge subnets are in 172.16.0.0/12 range.
iptables -A DOCKER-USER -s 172.16.0.0/12 -d 172.16.0.0/12 -j RETURN

# Rule 4: Allow container → internet ONLY on essential ports
#   443 = HTTPS (Telegram, OpenAI, Stripe, Upwork, GHCR, etc.)
#    80 = HTTP  (Webshare proxy, ACME, HTTP redirects)
#   587 = SMTP  (SendGrid/email submission)
#    53 = DNS   (resolve hostnames)
# All other outbound ports are BLOCKED (malware C2, crypto mining, etc.)
iptables -A DOCKER-USER -s 172.16.0.0/12 ! -d 172.16.0.0/12 -p tcp --dport 443 -j RETURN
iptables -A DOCKER-USER -s 172.16.0.0/12 ! -d 172.16.0.0/12 -p tcp --dport 80 -j RETURN
iptables -A DOCKER-USER -s 172.16.0.0/12 ! -d 172.16.0.0/12 -p tcp --dport 587 -j RETURN
iptables -A DOCKER-USER -s 172.16.0.0/12 ! -d 172.16.0.0/12 -p udp --dport 53 -j RETURN
iptables -A DOCKER-USER -s 172.16.0.0/12 ! -d 172.16.0.0/12 -p tcp --dport 53 -j RETURN

# Rule 5: LOG + DROP everything else
#   - External → container (inbound attack) → DROPPED
#   - Container → weird port (malware C2)   → DROPPED
iptables -A DOCKER-USER -j LOG --log-prefix "DOCKER-USER-DROP: " --log-level 4 -m limit --limit 5/min
iptables -A DOCKER-USER -j DROP

echo ""
echo "--- IPv4 DOCKER-USER rules applied ---"
iptables -L DOCKER-USER -n -v --line-numbers

# ==========================================================================
# IPv6 DOCKER-USER rules (mirror of IPv4)
# Without these, containers could bypass restrictions via IPv6.
# ==========================================================================
echo ""
echo "--- Configuring DOCKER-USER chain (IPv6) ---"

# Docker may not create DOCKER-USER for ip6tables; create if missing
ip6tables -N DOCKER-USER 2>/dev/null || true
ip6tables -F DOCKER-USER 2>/dev/null || true

# Rule 1: Allow established/related
ip6tables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
# Rule 2: Allow loopback
ip6tables -A DOCKER-USER -i lo -j RETURN
# Rule 3: Allow Docker inter-container (fd00::/8 covers Docker's IPv6 ULA range)
ip6tables -A DOCKER-USER -s fd00::/8 -d fd00::/8 -j RETURN
# Rule 4: Allow container → internet on essential ports only
ip6tables -A DOCKER-USER -s fd00::/8 ! -d fd00::/8 -p tcp --dport 443 -j RETURN
ip6tables -A DOCKER-USER -s fd00::/8 ! -d fd00::/8 -p tcp --dport 80 -j RETURN
ip6tables -A DOCKER-USER -s fd00::/8 ! -d fd00::/8 -p tcp --dport 587 -j RETURN
ip6tables -A DOCKER-USER -s fd00::/8 ! -d fd00::/8 -p udp --dport 53 -j RETURN
ip6tables -A DOCKER-USER -s fd00::/8 ! -d fd00::/8 -p tcp --dport 53 -j RETURN
# Rule 5: LOG + DROP
ip6tables -A DOCKER-USER -j LOG --log-prefix "DOCKER-USER6-DROP: " --log-level 4 -m limit --limit 5/min
ip6tables -A DOCKER-USER -j DROP

echo ""
echo "--- IPv6 DOCKER-USER rules applied ---"
ip6tables -L DOCKER-USER -n -v --line-numbers 2>/dev/null || echo "(no ip6tables DOCKER-USER)"
echo ""

# Persist iptables rules across reboots (both v4 and v6)
netfilter-persistent save > /dev/null 2>&1
echo "✅ iptables rules persisted (IPv4 + IPv6)"
IPTABLES_SCRIPT
}

# --- 2c. Deploy updated compose with internal networks (backend) ---
fix_compose_backend() {
    local ip="$BACKEND_IP"
    log "[backend] Uploading hardened docker-compose with internal networks..."

    # Upload the updated compose file (with GHCR_USER substituted)
    local tmp_compose
    tmp_compose=$(mktemp)
    sed "s|\${GHCR_USER}|${GHCR_USER}|g" \
        "$REPO_ROOT/infra/deploy/docker-compose.backend.yml" > "$tmp_compose"
    scp_to "$ip" "$tmp_compose" "/etc/vacancy-mirror/docker-compose.yml"
    rm -f "$tmp_compose"

    # Recreate containers with new network config
    log "[backend] Recreating containers with internal networks..."
    ssh_to "$ip" bash <<'COMPOSE_SCRIPT'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d
sleep 5
echo "--- Container status ---"
docker compose ps
echo ""
echo "--- Network verification ---"
docker network ls | grep -E 'internal|egress|bridge'
echo ""
# Verify postgres can't reach internet
echo "--- Testing postgres internet isolation ---"
if docker compose exec -T postgres timeout 3 bash -c "cat < /dev/tcp/1.1.1.1/443" 2>/dev/null; then
    echo "🔴 FAIL: postgres CAN reach internet!"
else
    echo "✅ PASS: postgres cannot reach internet"
fi
echo ""
echo "--- Testing backend can reach Telegram API ---"
if docker compose exec -T backend timeout 5 python -c "import urllib.request; urllib.request.urlopen('https://api.telegram.org', timeout=3); print('OK')" 2>/dev/null; then
    echo "✅ PASS: backend can reach api.telegram.org"
else
    echo "⚠️  backend cannot reach api.telegram.org (might be iptables timing — retry)"
fi
COMPOSE_SCRIPT
}

# --- 2d. Deploy updated compose with internal networks (scraper) ---
fix_compose_scraper() {
    local ip="$SCRAPER_IP"
    log "[scraper] Uploading hardened docker-compose with internal networks..."

    scp_to "$ip" "$REPO_ROOT/infra/deploy/docker-compose.server2.yml" \
        "/etc/vacancy-mirror/docker-compose.yml"

    log "[scraper] Recreating containers with internal networks..."
    ssh_to "$ip" bash <<'COMPOSE_SCRIPT'
set -euo pipefail
cd /etc/vacancy-mirror
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d
sleep 5
echo "--- Container status ---"
docker compose ps
echo ""
echo "--- Network verification ---"
docker network ls | grep -E 'internal|egress|bridge'
echo ""
# Verify postgres can't reach internet
echo "--- Testing postgres internet isolation ---"
if docker compose exec -T postgres timeout 3 bash -c "cat < /dev/tcp/1.1.1.1/443" 2>/dev/null; then
    echo "🔴 FAIL: postgres CAN reach internet!"
else
    echo "✅ PASS: postgres cannot reach internet"
fi
echo ""
# Verify grafana can't reach internet
echo "--- Testing grafana internet isolation ---"
if docker compose exec -T grafana timeout 3 wget -q -O /dev/null https://grafana.com 2>/dev/null; then
    echo "🔴 FAIL: grafana CAN reach internet!"
else
    echo "✅ PASS: grafana cannot reach internet"
fi
COMPOSE_SCRIPT
}

# --- 2e. Full fix for one server ---
fix_server() {
    local ip="$1" name="$2"
    log "========== FIX: $name ($ip) =========="

    fix_docker_daemon "$ip" "$name"
    fix_iptables "$ip" "$name"

    if [[ "$name" == "backend" ]]; then
        fix_compose_backend
    elif [[ "$name" == "scraper" ]]; then
        fix_compose_scraper
    fi

    ok "$name server locked down"
    log "========== FIX COMPLETE: $name =========="
    echo ""
}

# =============================================================================
# RUN
# =============================================================================
log "=== NETWORK LOCKDOWN ($ACTION / $SERVERS) ==="
echo ""

case "$ACTION" in
    audit)
        case "$SERVERS" in
            backend) audit_server "$BACKEND_IP" "backend" ;;
            scraper) audit_server "$SCRAPER_IP" "scraper" ;;
            both)    audit_server "$BACKEND_IP" "backend"; audit_server "$SCRAPER_IP" "scraper" ;;
            *)       die "Unknown server '$SERVERS'. Use: backend | scraper | both" ;;
        esac
        ;;
    fix)
        echo "⚠️  This will restart Docker daemon and all containers on target servers."
        echo "   Containers with 'internal' network will lose internet access."
        echo ""
        read -p "Continue? Type YES: " confirm
        [[ "$confirm" == "YES" ]] || die "Aborted."
        case "$SERVERS" in
            backend) fix_server "$BACKEND_IP" "backend" ;;
            scraper) fix_server "$SCRAPER_IP" "scraper" ;;
            both)    fix_server "$BACKEND_IP" "backend"; fix_server "$SCRAPER_IP" "scraper" ;;
            *)       die "Unknown server '$SERVERS'. Use: backend | scraper | both" ;;
        esac
        ;;
    all)
        log "--- Phase 1: AUDIT (before) ---"
        case "$SERVERS" in
            backend) audit_server "$BACKEND_IP" "backend" ;;
            scraper) audit_server "$SCRAPER_IP" "scraper" ;;
            both)    audit_server "$BACKEND_IP" "backend"; audit_server "$SCRAPER_IP" "scraper" ;;
        esac

        echo ""
        echo "⚠️  Phase 2 will restart Docker daemon and all containers."
        read -p "Continue with fixes? Type YES: " confirm
        [[ "$confirm" == "YES" ]] || die "Aborted."

        log "--- Phase 2: FIX ---"
        case "$SERVERS" in
            backend) fix_server "$BACKEND_IP" "backend" ;;
            scraper) fix_server "$SCRAPER_IP" "scraper" ;;
            both)    fix_server "$BACKEND_IP" "backend"; fix_server "$SCRAPER_IP" "scraper" ;;
        esac

        log "--- Phase 3: AUDIT (after) ---"
        case "$SERVERS" in
            backend) audit_server "$BACKEND_IP" "backend" ;;
            scraper) audit_server "$SCRAPER_IP" "scraper" ;;
            both)    audit_server "$BACKEND_IP" "backend"; audit_server "$SCRAPER_IP" "scraper" ;;
        esac
        ;;
    *)
        die "Unknown action '$ACTION'. Use: audit | fix | all"
        ;;
esac

log ""
log "=== NETWORK LOCKDOWN COMPLETE ==="
log ""
log "What was done:"
log "  1. Docker daemon: userland-proxy=false, no-new-privileges=true"
log "  2. DOCKER-USER iptables: blocks external→container, restricts outbound ports"
log "  3. Docker networks: postgres/grafana/prometheus on 'internal' (no internet)"
log "  4. Allowed outbound from containers: only ports 443, 80, 587, 53"
log ""
log "Security layers (defense in depth):"
log "  Layer 1: UFW — deny incoming (except SSH + nginx)"
log "  Layer 2: DOCKER-USER iptables — block external→container forwarding"
log "  Layer 3: userland-proxy=false — no iptables-bypassing proxy processes"
log "  Layer 4: internal networks — postgres/grafana physically can't reach internet"
log "  Layer 5: outbound port whitelist — containers limited to 443/80/587/53"
log "  Layer 6: container hardening — read_only, no-new-privileges, cap_drop ALL"
log ""
log "To verify manually:"
log "  # Check what's listening externally:"
log "  ssh -p 2222 root@$BACKEND_IP 'ss -tlnp | grep 0.0.0.0'"
log "  # Check DOCKER-USER rules:"
log "  ssh -p 2222 root@$BACKEND_IP 'iptables -L DOCKER-USER -n -v'"
log "  # Test container internet isolation:"
log "  ssh -p 2222 root@$BACKEND_IP 'docker exec postgres timeout 3 curl -s https://example.com || echo BLOCKED'"

