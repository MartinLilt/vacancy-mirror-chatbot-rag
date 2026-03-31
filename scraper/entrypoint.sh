#!/bin/bash
# Entrypoint for scraper container — starts cron daemon

set -e

echo "🚀 Scraper container starting..."
echo "   Time: $(date)"
echo "   Timezone: $(cat /etc/timezone 2>/dev/null || echo 'UTC')"

# Create log file
touch /var/log/scraper.log
echo "📝 Log file: /var/log/scraper.log"

# Create state directory
mkdir -p /app/data
echo "💾 State directory: /app/data"

# Show cron schedule
echo ""
echo "📅 Cron schedule:"
crontab -l
echo ""

# Start cron in foreground
echo "⏰ Starting cron daemon..."
exec cron -f
