# Phase 2 Manual Deployment Instructions

## Шаг 1: Подключитесь к серверу

```bash
ssh root@178.104.113.58
```

Введите root-пароль от Hetzner VPS.

---

## Шаг 2: Обновите .env файл

```bash
cd /opt/vacancy-mirror
nano .env
```

Добавьте в конец файла:

```env
# Phase 2: Webshare Residential Proxy + Session Persistence
PROXY_URL=http://yredwczd-1-country-US-session-upwork123:1500jnrpopto@p.webshare.io:80
CHROME_USER_DATA_DIR=/app/data/chrome_profile
COOKIE_BACKUP_PATH=/app/data/session_cookies.json
```

Сохраните: `Ctrl+X`, потом `Y`, потом `Enter`.

---

## Шаг 3: Создайте rotation script

```bash
mkdir -p /opt/vacancy-mirror/scraper/scripts

cat > /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/vacancy-mirror/.env"
SESSION_ID="upwork-$(date +%Y%m%d-%H%M%S)"

# Update PROXY_URL with new session ID
sed -i "s/session-[^:]*/session-${SESSION_ID}/" "$ENV_FILE"

echo "[$(date)] Rotated Webshare session to: ${SESSION_ID}"
EOF

chmod +x /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh
```

---

## Шаг 4: Настройте cron job

```bash
mkdir -p /opt/vacancy-mirror/logs

crontab -e
```

Добавьте в конец файла:

```cron
*/30 * * * * /opt/vacancy-mirror/scraper/scripts/rotate_webshare_session.sh >> /opt/vacancy-mirror/logs/cron.log 2>&1
```

Сохраните: `Ctrl+X`, потом `Y`, потом `Enter`.

---

## Шаг 5: Протестируйте proxy

```bash
curl --proxy "http://yredwczd-1-country-US-session-test:1500jnrpopto@p.webshare.io:80" https://api.ipify.org
```

**Ожидаемый результат:** residential IP (например `203.x.x.x`), НЕ `178.104.113.58`

---

## Шаг 6: Перезапустите scraper

```bash
cd /opt/vacancy-mirror
docker-compose restart scraper
```

---

## Шаг 7: Запустите тестовый scrape

```bash
docker-compose exec scraper python -m scraper.cli scrape \
    --uid 531770282580668418 \
    --label "Web Dev" \
    --max-pages 1 \
    --delay-min 5 \
    --delay-max 10
```

---

## ✅ Проверка успеха

Если всё работает правильно, вы увидите:

```
INFO - Using proxy: http://yredwczd-1-country-US-session-upwork123:...@p.webshare.io:80
INFO - Applying stealth patches...
INFO - Browser started.
INFO - Page   1/1 — 50 jobs fetched (checkpoint saved)
```

**Никаких Cloudflare challenges!** 🎉

---

## Troubleshooting

### Проблема: Proxy не работает

```bash
# Проверьте credentials:
curl --proxy "http://yredwczd-1-country-US-session-test:1500jnrpopto@p.webshare.io:80" -v https://api.ipify.org
```

### Проблема: Cron не ротирует

```bash
# Проверьте логи:
tail -f /opt/vacancy-mirror/logs/cron.log

# Проверьте crontab:
crontab -l
```

### Проблема: Scraper не видит PROXY_URL

```bash
# Проверьте .env:
cat /opt/vacancy-mirror/.env | grep PROXY_URL

# Перезапустите контейнер:
docker-compose restart scraper
```
