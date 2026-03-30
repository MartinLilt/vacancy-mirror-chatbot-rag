FROM python:3.13-slim

# Install Chromium + all runtime dependencies in one layer.
# Chromium works on both amd64 and arm64 (Apple Silicon via Docker Desktop).
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    curl \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    xdg-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENV CHROME_PATH=/usr/bin/chromium
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "scraper.cli"]
