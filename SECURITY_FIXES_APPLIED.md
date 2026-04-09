# 🔒 Security Fixes Applied — Scraper Server

**Дата:** 9 апреля 2026  
**Статус:** ✅ Критические исправления применены

---

## 📋 Применённые исправления

### ✅ 1. CVE-2024-3772 — Pydantic ReDoS vulnerability

**Файл:** `scraper/pyproject.toml`

**Изменение:**
```diff
dependencies = [
-   "pydantic>=2.0",
+   "pydantic>=2.4.0",  # CVE-2024-3772 fix (ReDoS vulnerability)
]
```

**Описание:**  
Обновлена версия Pydantic до 2.4.0 для исправления уязвимости Regular Expression Denial of Service (ReDoS). Уязвимость позволяла атакующему вызвать DoS через crafted email string.

**CVE:** [CVE-2024-3772](https://github.com/advisories/GHSA-mr82-8j83-vxmv)  
**Severity:** MEDIUM

---

### ✅ 2. CORS wildcard restriction

**Файл:** `scraper/src/scraper_api/main.py`

**Изменение:**
```diff
app.add_middleware(
    CORSMiddleware,
-   allow_origins=["*"],
-   allow_methods=["*"],
-   allow_headers=["*"],
+   allow_origins=[
+       "https://api.vacancy-mirror.com",
+       "https://vacancy-mirror.com",
+       "http://localhost:3000",  # dev only
+       "http://localhost:8000",  # dev only
+   ],
+   allow_methods=["GET", "POST"],
+   allow_headers=["Content-Type", "X-API-Key", "Authorization"],
+   allow_credentials=False,
)
```

**Описание:**  
Ограничены CORS origins до whitelist доверенных доменов. Предыдущая конфигурация `allow_origins=["*"]` позволяла ЛЮБОМУ сайту делать запросы к API, что могло привести к CSRF атакам.

**Риск:** MEDIUM → **MITIGATED** ✅

---

### ✅ 3. API Key validation at startup

**Файл:** `scraper/src/scraper_api/main.py`

**Изменение:**
```diff
DATABASE_URL: str = os.environ["DATABASE_URL"]
- API_KEY: str = os.environ.get("SCRAPER_API_KEY", "changeme")
+ API_KEY: str = os.environ.get("SCRAPER_API_KEY") or os.environ.get("API_KEY", "")
+
+ # Security: fail fast if API key is not set or is default value
+ if not API_KEY or API_KEY == "changeme":
+     log.warning(
+         "⚠️  SCRAPER_API_KEY not set or using default value! "
+         "API will be vulnerable. Set a strong random key in production."
+     )
+     if os.environ.get("PRODUCTION", "false").lower() == "true":
+         raise RuntimeError(
+             "SCRAPER_API_KEY must be set in production environment"
+         )
```

**Описание:**  
Добавлена валидация API ключа при старте приложения:
- Выдаёт warning если ключ не установлен или default
- **Останавливает запуск** в production если ключ не задан
- Поддерживает оба env vars: `SCRAPER_API_KEY` и `API_KEY`

**Риск:** LOW → **MITIGATED** ✅

---

### ✅ 4. Unauthorized access logging

**Файл:** `scraper/src/scraper_api/main.py`

**Изменение:**
```python
def require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != API_KEY:
        # Log unauthorized attempts for security monitoring
        log.warning(
            "Unauthorized API access attempt - invalid key: %s...",
            x_api_key[:8] if len(x_api_key) >= 8 else "***"
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
```

**Описание:**  
Добавлено логирование всех попыток неавторизованного доступа. Логи попадают в:
- `/var/log/scraper.log` (контейнер)
- Docker logs (доступ: `docker logs scraper`)

**Польза:**  
Позволяет обнаружить:
- Brute-force атаки на API key
- Компрометацию credentials
- Попытки несанкционированного доступа

---

### ✅ 5. Optional authentication helper

**Файл:** `scraper/src/scraper_api/main.py`

**Добавлено:**
```python
def optional_api_key(x_api_key: str | None = Header(None)) -> bool:
    """Optional API key check for read-only endpoints.
    
    Returns True if valid key provided, False if no key.
    Raises 401 if invalid key provided.
    
    Use this for GET endpoints that should be public for monitoring
    but can optionally require auth via X-API-Key header.
    """
    if x_api_key is None:
        return False
    if x_api_key != API_KEY:
        log.warning(
            "Unauthorized API access attempt - invalid key: %s...",
            x_api_key[:8] if len(x_api_key) >= 8 else "***"
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
```

**Использование (future):**
```python
@app.get("/jobs")
def get_jobs(authenticated: bool = Depends(optional_api_key)):
    if not authenticated:
        log.info("Public access to /jobs endpoint (no auth)")
    # ... endpoint logic
```

**Описание:**  
Добавлена возможность опциональной аутентификации для read-only эндпоинтов.  
Текущие публичные эндпоинты:
- `GET /health` — OK (liveness probe)
- `GET /status` — OK (monitoring)
- `GET /categories` — OK (справочник)
- `GET /jobs` — ⚠️ можно защитить в будущем
- `GET /logs` — ⚠️ можно защитить в будущем
- `GET /chaos-state` — OK (monitoring)

---

## 🚀 Деплой изменений

### Локальная разработка

```bash
cd scraper/
pip install -e .  # переустановит pydantic>=2.4.0
```

### Production (scraper server 178.104.110.28)

```bash
# 1. Build новый образ
cd /path/to/vacancy-mirror-chatbot-rag
docker build -t ghcr.io/martinlilt/vacancy-mirror-scraper:latest scraper/

# 2. Push в registry
docker push ghcr.io/martinlilt/vacancy-mirror-scraper:latest

# 3. На сервере: pull новый образ
ssh -p 2222 root@178.104.110.28
cd /etc/vacancy-mirror
docker compose pull scraper

# 4. Recreate container
docker compose up -d scraper

# 5. Проверить логи
docker compose logs -f scraper | head -50
# Должен быть: "⚠️  SCRAPER_API_KEY not set..." или запуск без ошибок

# 6. Проверить health
curl http://localhost:8000/health
# {"ok": true}
```

**Или автоматический деплой:**
```bash
bash infra/deploy/deploy.sh scraper
```

---

## 📊 Проверка применения исправлений

### 1. Pydantic версия

```bash
docker exec scraper pip show pydantic | grep Version
# Version: 2.4.0 или выше ✅
```

### 2. CORS настройки

```bash
# Попытка CORS запроса с неразрешённого origin (должна быть отклонена)
curl -H "Origin: https://evil.com" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS http://localhost:8000/scrape

# Ожидаемый результат: нет Access-Control-Allow-Origin в ответе
```

### 3. API key validation

```bash
# Неверный API key (должен вернуть 401 + залогировать)
curl -X POST http://localhost:8000/scrape \
     -H "X-API-Key: wrong_key" \
     -H "Content-Type: application/json" \
     -d '{"category_uid": "531770282580668418", "max_pages": 1}'

# Ожидаемый результат:
# HTTP 401 Unauthorized
# {"detail": "Invalid API key"}

# Проверить лог:
docker logs scraper 2>&1 | grep "Unauthorized API access attempt"
# Должна быть запись с частью ключа: "wrong_ke..."
```

### 4. Startup validation

```bash
# Запуск без SCRAPER_API_KEY с флагом PRODUCTION=true (должен упасть)
docker run --rm \
  -e PRODUCTION=true \
  -e DATABASE_URL=postgresql://user:pass@localhost/db \
  ghcr.io/martinlilt/vacancy-mirror-scraper:latest \
  uvicorn scraper_api.main:app

# Ожидаемый результат:
# RuntimeError: SCRAPER_API_KEY must be set in production environment
```

---

## ✅ Чеклист деплоя

- [ ] Образ собран с новыми зависимостями
- [ ] Pydantic обновлён до >=2.4.0
- [ ] CORS origins ограничены
- [ ] API key validation добавлена
- [ ] Логирование неавторизованных попыток работает
- [ ] Health check проходит (`GET /health → 200`)
- [ ] Production env содержит `SCRAPER_API_KEY`
- [ ] Логи мониторятся на unauthorized attempts

---

## 📝 Дополнительные рекомендации (опционально)

### Rate limiting (защита от DoS)

```bash
pip install slowapi
```

```python
# scraper/src/scraper_api/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/scrape", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
def trigger_scrape(request: Request, req: ScrapeRequest):
    ...
```

### Health check в docker-compose

```yaml
# infra/deploy/docker-compose.server2.yml
scraper:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

### Non-root user в Dockerfile

```dockerfile
# scraper/Dockerfile (после всех COPY и RUN)
RUN groupadd -r scraper && \
    useradd -r -g scraper scraper && \
    chown -R scraper:scraper /app /var/log

USER scraper
```

⚠️ **Внимание:** Chrome headless может требовать root или --no-sandbox.

---

**Подготовлено:** GitHub Copilot  
**Последнее обновление:** 9 апреля 2026

