# 🚀 Manual Deployment Guide — Security Fixes

**Дата:** 9 апреля 2026  
**Цель:** Deploy security fixes на оба сервера

---

## ⚡ Быстрый деплой (автоматический)

```bash
# Запустить автоматический deployment скрипт
cd /path/to/vacancy-mirror-chatbot-rag
bash deploy_security_fixes.sh
```

**Время:** ~15-20 минут  
**Что делает:**
- ✅ Pre-flight проверки (SSH, Docker, GHCR)
- ✅ Build всех образов (scraper, backend, api)
- ✅ Push в GitHub Container Registry
- ✅ Deploy на scraper server
- ✅ Deploy на backend server
- ✅ Health checks

---

## 📋 Ручной деплой (пошагово)

### Шаг 1: Pre-flight проверки

```bash
# Проверить SSH ключ
ls -la ~/.ssh/vacancy_mirror_deploy

# Проверить Docker
docker --version

# Проверить GHCR login
docker info | grep ghcr.io

# Если не залогинены:
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

---

### Шаг 2: Build образов

```bash
cd /path/to/vacancy-mirror-chatbot-rag

# Build scraper
docker build -t ghcr.io/martinlilt/vacancy-mirror-scraper:latest scraper/

# Build backend
docker build -t ghcr.io/martinlilt/vacancy-mirror-backend:latest backend/

# Build API
docker build -t ghcr.io/martinlilt/vacancy-mirror-api:latest web/api/
```

**Время:** ~10-15 минут (зависит от кеша)

---

### Шаг 3: Push в GHCR

```bash
# Push scraper
docker push ghcr.io/martinlilt/vacancy-mirror-scraper:latest

# Push backend
docker push ghcr.io/martinlilt/vacancy-mirror-backend:latest

# Push API
docker push ghcr.io/martinlilt/vacancy-mirror-api:latest
```

**Время:** ~5-10 минут (зависит от интернета)

---

### Шаг 4: Deploy Scraper Server

```bash
# SSH в scraper server
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28

# На сервере:
cd /etc/vacancy-mirror

# Pull новый образ
docker compose pull scraper

# Recreate container
docker compose up -d scraper

# Проверить статус
docker compose ps scraper
docker compose logs --tail 50 scraper

# Health check
curl http://localhost:8000/health
# → {"ok": true}

# Проверить версию Pydantic
docker exec scraper pip show pydantic | grep Version
# → Version: 2.4.0 или выше ✅

# Выход
exit
```

**Downtime:** ~10 секунд

---

### Шаг 5: Deploy Backend Server

```bash
# SSH в backend server
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58

# На сервере:
cd /etc/vacancy-mirror

# Pull новые образы
docker compose pull backend assistant-infer-1 assistant-infer-2 assistant-infer-3 support-webhook api

# Recreate containers
docker compose up -d

# Проверить статус
docker compose ps
docker compose logs --tail 50 backend

# Health checks
curl http://localhost:8000/health
# → {"ok": true, ...}

# Проверить версии
docker exec backend pip show aiohttp | grep Version
# → Version: 3.13.4 или выше ✅

docker exec backend pip show scikit-learn | grep Version
# → Version: 1.5.0 или выше ✅

# Telegram bot должен работать
docker compose logs --tail 100 backend | grep -i "started\|running\|ready"

# Выход
exit
```

**Downtime:** ~30 секунд

---

## ✅ Verification

### Scraper Server

```bash
# SSH
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/status

# Check Pydantic version
docker exec scraper pip show pydantic

# Check logs
docker compose logs -f scraper

# Exit
exit
```

**Ожидаемые результаты:**
- ✅ Health endpoint returns `{"ok": true}`
- ✅ Pydantic version >= 2.4.0
- ✅ Нет ошибок в логах
- ✅ CORS whitelist применён (проверить код)

---

### Backend Server

```bash
# SSH
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58

# Check health
curl http://localhost:8000/health

# Check versions
docker exec backend pip show aiohttp scikit-learn

# Check containers
docker compose ps
# → Все контейнеры Up

# Check logs
docker compose logs -f backend
docker compose logs -f assistant-infer-1

# Test Telegram bot (отправить /start в бота)

# Exit
exit
```

**Ожидаемые результаты:**
- ✅ API health endpoint работает
- ✅ aiohttp >= 3.13.4
- ✅ scikit-learn >= 1.5.0
- ✅ Все 6 контейнеров Up
- ✅ Backend logs без errors
- ✅ Telegram bot отвечает

---

## 🔍 Troubleshooting

### Build failed

```bash
# Очистить Docker cache
docker builder prune -af

# Пересобрать
docker build --no-cache -t IMAGE_NAME .
```

---

### Push failed (authentication)

```bash
# Re-login в GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Или создать Personal Access Token:
# GitHub → Settings → Developer Settings → Personal Access Tokens → Classic
# Scope: write:packages, read:packages, delete:packages
```

---

### SSH connection failed

```bash
# Проверить SSH ключ
ls -la ~/.ssh/vacancy_mirror_deploy
chmod 600 ~/.ssh/vacancy_mirror_deploy

# Проверить connectivity
ping 178.104.110.28
ping 178.104.113.58

# Проверить SSH порт
nc -zv 178.104.110.28 2222
nc -zv 178.104.113.58 2222
```

---

### Container не запускается

```bash
# На сервере:
docker compose logs CONTAINER_NAME

# Проверить image
docker images | grep vacancy-mirror

# Пересоздать
docker compose down CONTAINER_NAME
docker compose up -d CONTAINER_NAME
```

---

### Health check failed

```bash
# Проверить порты
netstat -tlnp | grep 8000

# Проверить nginx
systemctl status nginx
nginx -t

# Проверить logs
docker compose logs --tail 100 CONTAINER_NAME
```

---

## 📊 Rollback (если что-то пошло не так)

### Scraper

```bash
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
cd /etc/vacancy-mirror

# Pull предыдущую версию
docker pull ghcr.io/martinlilt/vacancy-mirror-scraper:security-PREVIOUS_DATE

# Update docker-compose.yml временно
# image: ghcr.io/martinlilt/vacancy-mirror-scraper:security-PREVIOUS_DATE

docker compose up -d scraper
```

---

### Backend

```bash
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.113.58
cd /etc/vacancy-mirror

# Pull предыдущую версию
docker pull ghcr.io/martinlilt/vacancy-mirror-backend:security-PREVIOUS_DATE

# Update docker-compose.yml
docker compose up -d
```

---

## ⏱️ Estimated Timeline

| Step | Time | Downtime |
|------|------|----------|
| **Build образов** | 10-15 min | 0 |
| **Push в GHCR** | 5-10 min | 0 |
| **Deploy scraper** | 2 min | ~10 sec |
| **Deploy backend** | 3 min | ~30 sec |
| **Verification** | 5 min | 0 |
| **ИТОГО** | **~25-35 min** | **~40 sec** |

---

## 📝 Checklist

### Pre-deployment
- [ ] SSH ключ доступен
- [ ] Docker установлен
- [ ] GHCR login успешен
- [ ] SSH connectivity проверена
- [ ] Backup создан (опционально)

### Scraper deployment
- [ ] Образ собран
- [ ] Образ запушен в GHCR
- [ ] Container пересоздан
- [ ] Health check passed
- [ ] Pydantic 2.4.0+ установлен
- [ ] Логи чистые

### Backend deployment
- [ ] Образы собраны (backend, api)
- [ ] Образы запушены в GHCR
- [ ] Все контейнеры пересозданы
- [ ] Health checks passed
- [ ] aiohttp 3.13.4+ установлен
- [ ] scikit-learn 1.5.0+ установлен
- [ ] Telegram bot отвечает
- [ ] Логи чистые

### Post-deployment
- [ ] Мониторинг проверен (Grafana)
- [ ] Документация обновлена
- [ ] Team уведомлён
- [ ] Deployment tag создан в Git

---

## 🎯 Success Criteria

✅ **Scraper:**
- Health endpoint возвращает 200 OK
- Pydantic >= 2.4.0
- CORS whitelist применён
- API validation работает
- Логи без errors

✅ **Backend:**
- Health endpoint возвращает 200 OK
- aiohttp >= 3.13.4 (24 CVE fixed!)
- scikit-learn >= 1.5.0
- Multi-stage build применён
- Non-root user работает
- Telegram bot отвечает на /start
- Assistant-infer replicas Up
- Webhook обрабатывает requests

✅ **Оба сервера:**
- Downtime < 1 минута
- Нет critical errors в логах
- Monitoring работает
- Security fixes применены

---

**Подготовлено:** GitHub Copilot  
**Дата:** 9 апреля 2026

