#!/usr/bin/env bash
# Run the Upwork scraper for all known categories.
# Called manually or by cron (when enabled).
set -euo pipefail

IMAGE=ghcr.io/martinlilt/vacancy-mirror-scraper:latest

# Pull latest image before running
docker pull "$IMAGE" 2>&1 | tail -3

docker run --rm \
  --env-file /etc/vacancy-mirror/scraper.env \
  --shm-size=512m \
  "$IMAGE" \
  python -m scraper.cli scrape-categories
