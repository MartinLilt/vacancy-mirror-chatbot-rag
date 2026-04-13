FROM python:3.13-slim

# Install Chromium + cron + supervisor + runtime deps in one layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    cron \
    curl \
    jq \
    supervisor \
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
COPY scripts/ scripts/
COPY crontab /tmp/crontab-user
COPY crontab.crond /etc/cron.d/scraper-cron
COPY entrypoint.sh /app/entrypoint.sh
COPY supervisord.conf /etc/supervisor/conf.d/scraper.conf

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Setup cron (dual approach: user crontab for schedule-API + cron.d for execution)
# The cron.d file needs SHELL, PATH, and a username field so Debian cron
# can execute it even when capabilities are restricted (cap_drop: ALL +
# cap_add: SETUID/SETGID/DAC_OVERRIDE/AUDIT_WRITE in docker-compose).
RUN chmod 0644 /etc/cron.d/scraper-cron && \
    crontab /tmp/crontab-user && \
    rm /tmp/crontab-user && \
    chmod +x /app/entrypoint.sh && \
    chmod +x /app/scripts/scraper_runner.sh && \
    chmod +x /app/scripts/chaos_runner.sh

# Create state directory (will be mounted as volume)
RUN mkdir -p /app/data

ENV CHROME_PATH=/usr/bin/chromium
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# supervisord manages: cron + scraper-api (uvicorn)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/scraper.conf"]
