# =============================================================================

# Deployment Guide — vacancy-mirror-chatbot-rag

# =============================================================================

#

# Architecture

# ------------

# server-backend (cx22, ~4€/mo)

# ├── postgres (pgvector:pg16) — persistent DB

# └── backend (telegram bot) — ghcr.io image

#

# server-scraper (cx22, ~4€/mo)

# └── scraper (chromium + nodriver) — runs via daily cron

# connects to postgres on server-backend via its public IP

#

# Images are stored in GitHub Container Registry (ghcr.io) — free for public

# repos, $0/mo for private repos up to 500 MB.

#

# =============================================================================

# Prerequisites

# =============================================================================

#

# 1. hcloud CLI — already installed (hcloud v1.62.0)

# Login: hcloud context create vacancy-mirror

# (paste your Hetzner API token)

#

# 2. GitHub Personal Access Token (PAT)

# Go to: https://github.com/settings/tokens

# Scopes needed:

# - write:packages (to push images)

# - read:packages (to pull on servers)

# Save it — you'll need it as GHCR_TOKEN.

#

# 3. Docker Desktop running locally (for build + push).

#

# =============================================================================

# Step 1 — Set environment variables

# =============================================================================

#

# export HCLOUD_TOKEN=... # from https://console.hetzner.cloud

# export GHCR_USER=MartinLilt # your GitHub username

# export GHCR*TOKEN=ghp*... # GitHub PAT (write:packages)

# export DB_PASSWORD=... # strong random password

# export OPENAI_API_KEY=sk-...

# export TELEGRAM_BOT_TOKEN=...

# export OPENAI_MODEL=gpt-4.1-mini # optional

#

# =============================================================================

# Step 2 — Build & push images to ghcr.io

# =============================================================================

#

# bash infra/deploy/push-images.sh

#

# This builds both images for linux/amd64 (Hetzner runs amd64) and pushes

# them to ghcr.io/<GHCR_USER>/vacancy-mirror-{backend,scraper}:latest

#

# NOTE: Hetzner servers are x86_64 (amd64), but your Mac is arm64.

# The --platform linux/amd64 flag in push-images.sh handles the cross-build.

#

# =============================================================================

# Step 3 — Provision servers (first time only)

# =============================================================================

#

# hcloud context use vacancy-mirror # select your project

# bash infra/deploy/provision.sh

#

# This will:

# - Create SSH key and upload to Hetzner

# - Create server-backend and server-scraper (CX22, Ubuntu 24.04)

# - Install Docker on both

# - Start postgres + backend on server-backend

# - Install daily cron on server-scraper (runs at 03:00 UTC)

# - Open firewall port 5432 on backend for scraper's IP only

#

# Total Hetzner cost: ~8€/month (2 × CX22)

#

# =============================================================================

# Step 4 — Deploy updates (after first provisioning)

# =============================================================================

#

# # 1. Push new images

# bash infra/deploy/push-images.sh

#

# # 2. Restart services

# bash infra/deploy/deploy.sh

#

# =============================================================================

# Useful commands after deployment

# =============================================================================

#

# SSH into servers:

# ssh -i ~/.ssh/vacancy_mirror_deploy root@<backend_ip>

# ssh -i ~/.ssh/vacancy_mirror_deploy root@<scraper_ip>

#

# Get server IPs:

# hcloud server list

#

# Backend logs:

# ssh root@<backend_ip> "cd /etc/vacancy-mirror && docker compose logs -f"

#

# Scraper logs:

# ssh root@<scraper_ip> "tail -f /var/log/scraper.log"

#

# Run scraper manually:

# ssh root@<scraper_ip> "/usr/local/bin/run-scraper.sh"

#

# Restart backend only (after push):

# ssh root@<backend_ip> "cd /etc/vacancy-mirror && docker compose pull backend && docker compose up -d --no-deps backend"

#

# Connect to postgres from local machine (via SSH tunnel):

# ssh -L 5433:localhost:5432 -i ~/.ssh/vacancy_mirror_deploy root@<backend_ip> -N &

# psql postgresql://app:<DB_PASSWORD>@localhost:5433/vacancy_mirror

#

# =============================================================================

# Environment files on servers

# =============================================================================

#

# server-backend: /etc/vacancy-mirror/backend.env

# DB_PASSWORD=...

# OPENAI_API_KEY=...

# OPENAI_MODEL=...

# TELEGRAM_BOT_TOKEN=...

#

# server-scraper: /etc/vacancy-mirror/scraper.env

# DB_URL=postgresql://app:<password>@<backend_ip>:5432/vacancy_mirror

# CHROME_PATH=/usr/bin/chromium

# LOG_LEVEL=INFO

#
