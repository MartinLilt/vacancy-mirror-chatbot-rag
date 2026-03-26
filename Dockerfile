# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# vacancy-mirror-chatbot-rag — scraper image
#
# Installs Google Chrome (stable) required by nodriver (real Chrome, anti-bot).
# The pipeline CLI is available as:
#   python -m vacancy_mirror_chatbot_rag.cli <command>
# ---------------------------------------------------------------------------

FROM python:3.13-slim AS base

# --- system dependencies and Chrome ------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        curl \
        gnupg \
        ca-certificates \
        fonts-liberation \
        libappindicator3-1 \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libgdk-pixbuf2.0-0 \
        libnspr4 \
        libnss3 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        xdg-utils \
    && wget -q -O /tmp/chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies ------------------------------------------------------
WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

# Install the package and all runtime dependencies.
# scikit-learn, numpy, sentence-transformers, nodriver are pulled
# in via pyproject.toml extras or installed explicitly here.
RUN pip install --no-cache-dir \
        "sentence-transformers>=3.0.1" \
        "scikit-learn>=1.8.0" \
        "numpy>=2.4.0" \
        "nodriver>=0.48.1" \
        "fake-useragent>=1.5.0" \
        "httpx>=0.28.0" \
    && pip install --no-cache-dir -e .

# --- runtime env defaults -----------------------------------------------------
# CATEGORY_UID  — Upwork parent category UID to scrape (required at runtime)
# PROXY_URL     — residential proxy, e.g. http://user:pass@host:port
# OPENAI_API_KEY / OPENAI_MODEL — for the naming step
# DATA_DIR      — mount a Hetzner Volume here to persist data across runs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    CHROME_PATH=/usr/bin/google-chrome

# --- data volume --------------------------------------------------------------
# Mount a Hetzner persistent Volume at /data to survive container restarts.
VOLUME ["/data"]

# --- entrypoint ---------------------------------------------------------------
# Default: run the full pipeline for the configured category.
# Override CMD at runtime for individual steps.
CMD ["python", "-m", "vacancy_mirror_chatbot_rag.cli", "--help"]
