#!/usr/bin/env bash
# =============================================================================
# setup_github_secrets.sh — Helper script to display GitHub Secrets
# =============================================================================
# This script helps you get the values needed for GitHub Secrets.
# You'll need to manually add them to GitHub repository settings.
#
# GitHub Repository Settings:
# https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/settings/secrets/actions
# =============================================================================

set -euo pipefail

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║          GitHub Secrets Setup — Vacancy Mirror                ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Load .env
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    source "$REPO_ROOT/.env"
    set +o allexport
fi

echo "📋 GitHub Secrets to add:"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret Name: BACKEND_SERVER_IP"
echo "Secret Value:"
echo "${BACKEND_SERVER_IP:-NOT_SET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret Name: SCRAPER_SERVER_IP"
echo "Secret Value:"
echo "${SCRAPER_SERVER_IP:-NOT_SET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret Name: SSH_PRIVATE_KEY"
echo "Secret Value:"
echo ""
SSH_KEY="${SSH_KEY:-$HOME/.ssh/vacancy_mirror_deploy}"

if [[ -f "$SSH_KEY" ]]; then
    echo "✅ SSH key found at: $SSH_KEY"
    echo ""
    echo "Copy the content below (including BEGIN/END lines):"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "$SSH_KEY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "❌ SSH key not found at: $SSH_KEY"
    echo "Please specify the correct path or create the key first."
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 How to add secrets to GitHub:"
echo ""
echo "1. Open: https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/settings/secrets/actions"
echo ""
echo "2. Click: 'New repository secret'"
echo ""
echo "3. Add each secret:"
echo "   - Name: BACKEND_SERVER_IP"
echo "     Value: ${BACKEND_SERVER_IP:-NOT_SET}"
echo ""
echo "   - Name: SCRAPER_SERVER_IP"
echo "     Value: ${SCRAPER_SERVER_IP:-NOT_SET}"
echo ""
echo "   - Name: SSH_PRIVATE_KEY"
echo "     Value: (copy from above)"
echo ""
echo "4. Done! ✅"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🧪 Test SSH connectivity:"
echo ""
echo "# Backend server"
echo "ssh -p 2222 -i $SSH_KEY root@${BACKEND_SERVER_IP:-SERVER_IP} 'echo OK'"
echo ""
echo "# Scraper server"
echo "ssh -p 2222 -i $SSH_KEY root@${SCRAPER_SERVER_IP:-SERVER_IP} 'echo OK'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ After adding secrets, you can run the deployment workflow!"
echo ""
echo "Go to: https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/actions"
echo "Select: 'Deploy to Production'"
echo "Click: 'Run workflow'"
echo ""

