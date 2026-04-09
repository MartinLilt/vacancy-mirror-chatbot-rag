#!/usr/bin/env bash
# =============================================================================
# harden_servers.sh — Post-incident security hardening for both servers.
#
# What it does:
#   1. SSH hardening (port 2222, fail2ban, max auth tries)
#   2. UFW firewall lockdown
#   3. Unattended security updates
#   4. auditd monitoring
#   5. Remove suspicious packages
#   6. Secure env files and Docker socket
#   7. Nginx rate limiting (backend only)
#
# Usage:
#   bash infra/deploy/harden_servers.sh [backend|scraper|all]
#
# ⚠️  After running: SSH port changes to 2222
#    ssh -i ~/.ssh/vacancy_mirror_deploy -p 2222 root@<ip>
# =============================================================================
set -euo pipefail

SSH_KEY="$HOME/.ssh/vacancy_mirror_deploy"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport; source "$REPO_ROOT/.env"; set +o allexport
fi
BACKEND_IP="${BACKEND_SERVER_IP:?Set BACKEND_SERVER_IP in .env}"
SCRAPER_IP="${SCRAPER_SERVER_IP:?Set SCRAPER_SERVER_IP in .env}"
NEW_SSH_PORT=2222
TARGET="${1:-all}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# =============================================================================
# Generic hardening (runs on any server)
# =============================================================================
harden_host() {
    local ip="$1" name="$2" extra_ufw_rules="${3:-}"
    log "===== Hardening $name ($ip) ====="

    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "root@${ip}" bash <<REMOTE_SCRIPT
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "--- [1/8] SSH hardening ---"
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.\$(date +%s)

# Change SSH port
sed -i 's/^#*Port .*/Port ${NEW_SSH_PORT}/' /etc/ssh/sshd_config
# Disable password auth
sed -i 's/^#*PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
# Root login key-only
sed -i 's/^#*PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
# Limit auth tries
grep -q '^MaxAuthTries' /etc/ssh/sshd_config && \
    sed -i 's/^MaxAuthTries .*/MaxAuthTries 3/' /etc/ssh/sshd_config || \
    echo 'MaxAuthTries 3' >> /etc/ssh/sshd_config
# Disable X11
sed -i 's/^#*X11Forwarding .*/X11Forwarding no/' /etc/ssh/sshd_config
# Idle timeout (10 min)
grep -q '^ClientAliveInterval' /etc/ssh/sshd_config && \
    sed -i 's/^ClientAliveInterval .*/ClientAliveInterval 300/' /etc/ssh/sshd_config || \
    echo 'ClientAliveInterval 300' >> /etc/ssh/sshd_config
grep -q '^ClientAliveCountMax' /etc/ssh/sshd_config && \
    sed -i 's/^ClientAliveCountMax .*/ClientAliveCountMax 2/' /etc/ssh/sshd_config || \
    echo 'ClientAliveCountMax 2' >> /etc/ssh/sshd_config
echo "  SSH config updated"

echo "--- [2/8] UFW firewall ---"
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow ${NEW_SSH_PORT}/tcp comment 'SSH'
${extra_ufw_rules}
echo "y" | ufw enable
echo "  UFW configured"

echo "--- [3/8] fail2ban ---"
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq fail2ban > /dev/null 2>&1
cat > /etc/fail2ban/jail.local <<'F2B'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
backend  = systemd

[sshd]
enabled  = true
port     = ${NEW_SSH_PORT}
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 7200
F2B
sed -i "s/port     = \\\${NEW_SSH_PORT}/port     = ${NEW_SSH_PORT}/" /etc/fail2ban/jail.local
systemctl enable fail2ban > /dev/null 2>&1
systemctl restart fail2ban
echo "  fail2ban configured (ban after 3 tries, 2h ban)"

echo "--- [4/8] Unattended security upgrades ---"
apt-get install -y -qq unattended-upgrades apt-listchanges > /dev/null 2>&1
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'UU'
Unattended-Upgrade::Allowed-Origins {
    "\${distro_id}:\${distro_codename}-security";
    "\${distro_id}ESMApps:\${distro_codename}-apps-security";
    "\${distro_id}ESM:\${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
UU
echo "  Auto security updates enabled"

echo "--- [5/8] auditd ---"
apt-get install -y -qq auditd audispd-plugins > /dev/null 2>&1
cat > /etc/audit/rules.d/hardening.rules <<'AUDIT'
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/ssh/sshd_config -p wa -k sshd_config
-w /etc/vacancy-mirror/ -p wa -k vacancy_mirror_config
-w /var/run/docker.sock -p wa -k docker_socket
-w /usr/bin/docker -p x -k docker_commands
-w /usr/bin/dockerd -p x -k docker_daemon
-w /usr/sbin/useradd -p x -k user_mgmt
-w /usr/sbin/userdel -p x -k user_mgmt
-w /etc/crontab -p wa -k cron
-w /etc/cron.d/ -p wa -k cron
-w /var/spool/cron/ -p wa -k cron
AUDIT
systemctl enable auditd > /dev/null 2>&1
systemctl restart auditd
echo "  auditd configured (monitoring critical files)"

echo "--- [6/8] Remove suspicious packages ---"
for pkg in squid squid-common telnetd rpcbind avahi-daemon cups; do
    dpkg -l "\$pkg" 2>/dev/null | grep -q '^ii' && {
        apt-get purge -y -qq "\$pkg" > /dev/null 2>&1
        echo "  Removed: \$pkg"
    } || true
done
apt-get autoremove -y -qq > /dev/null 2>&1

# Check for crypto miners
echo "  Checking for suspicious executables in /tmp, /var/tmp, /dev/shm..."
SUSPICIOUS=\$(find /tmp /var/tmp /dev/shm -type f -executable 2>/dev/null | head -5)
if [ -n "\$SUSPICIOUS" ]; then
    echo "  ⚠️  Found suspicious executables:"
    echo "\$SUSPICIOUS"
else
    echo "  ✅ No suspicious executables found"
fi

echo "--- [7/8] Secure env files and Docker socket ---"
chmod 600 /etc/vacancy-mirror/*.env 2>/dev/null || true
chmod 600 /etc/vacancy-mirror/chatwoot/.env 2>/dev/null || true
chmod 700 /etc/vacancy-mirror/
chmod 660 /var/run/docker.sock 2>/dev/null || true

# Limit journal size
sed -i 's/^#*SystemMaxUse=.*/SystemMaxUse=500M/' /etc/systemd/journald.conf
systemctl restart systemd-journald

echo "--- [8/8] Restart SSH on new port ---"
systemctl restart sshd
echo "✅ SSH restarted on port ${NEW_SSH_PORT}"

echo ""
echo "=== Final status ==="
ufw status verbose
echo ""
fail2ban-client status sshd 2>/dev/null || true
REMOTE_SCRIPT

    # Test SSH on new port
    log "Testing SSH on port ${NEW_SSH_PORT}..."
    sleep 3
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$SSH_KEY" -p "${NEW_SSH_PORT}" "root@${ip}" "echo 'SSH OK on port ${NEW_SSH_PORT}'" 2>/dev/null; then
        log "✅ SSH works on port ${NEW_SSH_PORT} for $name"
    else
        log "⚠️  SSH on port ${NEW_SSH_PORT} FAILED — try old port 22"
    fi
}

# =============================================================================
# Backend-specific: nginx rate limiting + security headers
# =============================================================================
harden_backend_nginx() {
    log "===== Backend: nginx hardening ====="
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" -p "${NEW_SSH_PORT}" "root@${BACKEND_IP}" bash <<'REMOTE'
set -euo pipefail

echo "--- Nginx rate limiting ---"
# Add rate limit zone in http block
if ! grep -q 'limit_req_zone' /etc/nginx/nginx.conf 2>/dev/null; then
    sed -i '/http {/a \    # Rate limiting (anti-DDoS)\n    limit_req_zone $binary_remote_addr zone=webhook:10m rate=10r/s;\n    limit_conn_zone $binary_remote_addr zone=connlimit:10m;\n\n    # Security headers\n    add_header X-Frame-Options DENY always;\n    add_header X-Content-Type-Options nosniff always;\n    add_header X-XSS-Protection "1; mode=block" always;\n    server_tokens off;' /etc/nginx/nginx.conf
    echo "  Added rate limiting and security headers to nginx.conf"
fi

# Add rate limit to webhook location in site config
SITE_CONF=""
for f in /etc/nginx/sites-enabled/vacancy-mirror /etc/nginx/sites-enabled/default; do
    [ -f "$f" ] && SITE_CONF="$f" && break
done

if [ -n "$SITE_CONF" ] && ! grep -q 'limit_req' "$SITE_CONF"; then
    sed -i '/location.*webhook/a \        limit_req zone=webhook burst=20 nodelay;\n        limit_conn connlimit 10;' "$SITE_CONF"
    echo "  Added rate limiting to webhook locations"
fi

nginx -t && systemctl reload nginx
echo "✅ Nginx hardened"
REMOTE
}

# =============================================================================
# RUN
# =============================================================================
log "=== SERVER HARDENING ==="
log "⚠️  SSH port will change to ${NEW_SSH_PORT}"
echo ""
read -p "Continue? Type YES: " confirm
[[ "$confirm" == "YES" ]] || die "Aborted."

case "$TARGET" in
    backend)
        harden_host "$BACKEND_IP" "backend" \
            "ufw allow 80/tcp comment 'HTTP nginx'; ufw allow 443/tcp comment 'HTTPS nginx'"
        harden_backend_nginx
        ;;
    scraper)
        harden_host "$SCRAPER_IP" "scraper" ""
        ;;
    all)
        harden_host "$BACKEND_IP" "backend" \
            "ufw allow 80/tcp comment 'HTTP nginx'; ufw allow 443/tcp comment 'HTTPS nginx'"
        harden_host "$SCRAPER_IP" "scraper" ""
        harden_backend_nginx
        ;;
    *)
        die "Unknown target '$TARGET'. Use: backend | scraper | all"
        ;;
esac

log ""
log "=== HARDENING COMPLETE ==="
log ""
log "⚠️  SSH port changed to ${NEW_SSH_PORT}. New commands:"
log "  ssh -i ~/.ssh/vacancy_mirror_deploy -p ${NEW_SSH_PORT} root@${BACKEND_IP}"
log "  ssh -i ~/.ssh/vacancy_mirror_deploy -p ${NEW_SSH_PORT} root@${SCRAPER_IP}"
log ""
log "Update these files to use -p ${NEW_SSH_PORT}:"
log "  - infra/deploy/deploy.sh"
log "  - infra/deploy/provision.sh"
log "  - infra/deploy/nuke_and_redeploy.sh"

