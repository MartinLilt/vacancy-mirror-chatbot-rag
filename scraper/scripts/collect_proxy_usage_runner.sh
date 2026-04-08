#!/bin/bash
# Cron-safe wrapper for Webshare usage collection.
# Cron may run with a minimal environment, so we recover required env vars
# from PID 1 (supervisord) when needed.

set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(tr '\0' '\n' < /proc/1/environ | grep -m1 '^DATABASE_URL=' | cut -d= -f2- || true)"
  export DATABASE_URL
fi

if [ -z "${WEBSHARE_API_KEY:-}" ]; then
  WEBSHARE_API_KEY="$(tr '\0' '\n' < /proc/1/environ | grep -m1 '^WEBSHARE_API_KEY=' | cut -d= -f2- || true)"
  export WEBSHARE_API_KEYF
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR collect-proxy-usage: DATABASE_URL is not set"
  exit 1
fi

if [ -z "${WEBSHARE_API_KEY:-}" ]; then
  echo "ERROR collect-proxy-usage: WEBSHARE_API_KEY is not set"
  exit 1
fi

/usr/local/bin/python -m scraper.cli collect-proxy-usage
