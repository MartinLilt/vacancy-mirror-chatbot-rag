# 🚀 CI/CD Pipeline — Deployment Guide

**Дата создания:** 9 апреля 2026  
**Статус:** ✅ Готов к использованию

---

## 📋 Что это?

Автоматический CI/CD pipeline для деплоя на Hetzner серверы через GitHub Actions.

**Возможности:**
- ✅ Автоматическая сборка Docker образов
- ✅ Push в GitHub Container Registry (GHCR)
- ✅ SSH deployment на production серверы
- ✅ Health checks после деплоя
- ✅ Выбор целевого сервера (backend, scraper, или оба)

---

## 🎯 Способы запуска

### 1️⃣ Ручной запуск (кнопка в GitHub)

**Самый простой способ!**

1. Открой https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/actions
2. Выбери workflow **"Deploy to Production"**
3. Нажми **"Run workflow"**
4. Выбери параметры:
   - **Branch:** `main` (по умолчанию)
   - **Deployment target:** 
     - `both` — оба сервера
     - `backend` — только backend
     - `scraper` — только scraper
   - **Confirm:** напиши `deploy`
5. Нажми **"Run workflow"**

**Время выполнения:** ~10-15 минут

---

### 2️⃣ Git Tag (версионирование)

**Для релизов:**

```bash
# Создать версионный тег
git tag -a v1.0.0 -m "Release v1.0.0: Security fixes"

# Запушить тег
git push origin v1.0.0
```

При push тега автоматически:
- ✅ Соберутся образы с тегом `v1.0.0`
- ✅ Задеплоятся на **оба сервера**
- ✅ Образы помечены как `latest` и `v1.0.0`

---

## 🔧 Настройка (один раз)

### GitHub Secrets

Нужно добавить следующие secrets в GitHub:

1. Открой https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/settings/secrets/actions

2. Добавь secrets:

```
BACKEND_SERVER_IP
Value: 178.104.110.28

SCRAPER_SERVER_IP  
Value: 89.167.27.149

SSH_PRIVATE_KEY
Value: (содержимое ~/.ssh/vacancy_mirror_deploy)
```

### Как получить SSH_PRIVATE_KEY:

```bash
# На локальной машине:
cat ~/.ssh/vacancy_mirror_deploy

# Скопируй весь вывод (включая -----BEGIN/END-----)
# Вставь в GitHub Secret
```

---

## 📊 Что происходит при деплое?

### Pipeline шаги:

```
1. Pre-flight Checks ✅
   └─ Проверка confirmation
   └─ Определение target (backend/scraper/both)

2. Build Images 🏗️
   ├─ Backend image (если нужен)
   ├─ API image (если нужен)  
   └─ Scraper image (если нужен)
   
3. Push to GHCR 📦
   └─ ghcr.io/martinlilt/vacancy-mirror-*
   
4. Deploy Backend 🚀 (если выбран)
   ├─ SSH → 178.104.110.28
   ├─ docker compose pull
   ├─ docker compose up -d
   └─ Health check
   
5. Deploy Scraper 🚀 (если выбран)
   ├─ SSH → 89.167.27.149
   ├─ docker compose pull scraper
   ├─ docker compose up -d scraper
   └─ Health check
   
6. Summary 📋
   └─ Итоговый отчёт
```

---

## 🎨 Примеры использования

### Деплой только backend

```yaml
Deployment target: backend
Confirm: deploy
```

Результат:
- ✅ Собирается backend + api
- ✅ Деплоится на 178.104.110.28
- ⏭️ Scraper пропускается

---

### Деплой только scraper

```yaml
Deployment target: scraper
Confirm: deploy
```

Результат:
- ✅ Собирается scraper
- ✅ Деплоится на 89.167.27.149
- ⏭️ Backend пропускается

---

### Деплой всего (полный)

```yaml
Deployment target: both
Confirm: deploy
```

Результат:
- ✅ Собираются все образы
- ✅ Деплоятся оба сервера
- ✅ Full deployment

---

## 📝 Логи и мониторинг

### Где смотреть логи?

1. **GitHub Actions UI:**
   - https://github.com/MartinLilt/vacancy-mirror-chatbot-rag/actions
   - Каждый job имеет подробные логи

2. **На сервере:**
   ```bash
   # Backend
   ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28
   docker compose logs -f backend
   
   # Scraper
   ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@89.167.27.149
   docker compose logs -f scraper
   ```

---

## ⚠️ Troubleshooting

### Deployment failed: SSH connection

**Проблема:** SSH не может подключиться к серверу

**Решение:**
```bash
# Проверь что SSH_PRIVATE_KEY secret правильный
# Проверь connectivity:
ssh -p 2222 -i ~/.ssh/vacancy_mirror_deploy root@178.104.110.28 "echo OK"
```

---

### Deployment failed: Image not found

**Проблема:** Docker не может найти образ

**Решение:**
- Проверь что build job успешно завершился
- Проверь GHCR: https://github.com/MartinLilt?tab=packages
- Re-run workflow

---

### Health check failed

**Проблема:** Health endpoint не отвечает

**Решение:**
```bash
# На сервере проверь:
docker compose ps
docker compose logs backend

# Возможно контейнер ещё стартует, подожди 30 сек
```

---

## 🔒 Безопасность

### Что защищено:

- ✅ SSH ключи в GitHub Secrets (encrypted)
- ✅ SSH порт 2222 (не стандартный)
- ✅ Deployment только с main branch
- ✅ Confirmation требуется ("deploy")
- ✅ Логи не показывают secrets

### Best practices:

- 🔐 SSH ключ храни только в GitHub Secrets
- 🔐 Не коммить `.env` файл
- 🔐 Используй workflow_dispatch для контроля
- 🔐 Проверяй логи после каждого деплоя

---

## 📈 Timeline

| Шаг | Время | Описание |
|-----|-------|----------|
| **Pre-flight** | 5 сек | Проверки |
| **Build Backend** | 5-8 мин | Multi-stage build |
| **Build Scraper** | 3-5 мин | Build образа |
| **Push images** | 1-2 мин | Upload в GHCR |
| **Deploy Backend** | 1-2 мин | SSH + pull + up |
| **Deploy Scraper** | 30 сек | SSH + pull + up |
| **ИТОГО** | **~10-15 мин** | Полный цикл |

---

## 🎯 Что дальше?

### Возможные улучшения:

1. **Rollback mechanism** — автоматический откат при ошибке
2. **Staging environment** — тестовый сервер перед production
3. **Slack notifications** — уведомления в Slack
4. **Health check retries** — повторные проверки
5. **Database migrations** — автоматические миграции

---

## 📚 Полезные ссылки

- **GitHub Actions Docs:** https://docs.github.com/en/actions
- **Docker Build Push:** https://github.com/docker/build-push-action
- **SSH Action:** https://github.com/appleboy/ssh-action
- **Repository:** https://github.com/MartinLilt/vacancy-mirror-chatbot-rag

---

## ✅ Checklist первого деплоя

- [ ] GitHub Secrets добавлены (BACKEND_SERVER_IP, SCRAPER_SERVER_IP, SSH_PRIVATE_KEY)
- [ ] SSH ключ валиден и работает
- [ ] `.env` файл не в git (в .gitignore)
- [ ] Тест SSH connectivity с локальной машины
- [ ] Запустить workflow вручную (test run)
- [ ] Проверить логи в GitHub Actions
- [ ] Проверить health endpoints после деплоя
- [ ] Проверить логи на серверах

---

**Создано:** GitHub Copilot  
**Дата:** 9 апреля 2026  
**Версия:** 1.0

🚀 **CI/CD ГОТОВ К ИСПОЛЬЗОВАНИЮ!**

