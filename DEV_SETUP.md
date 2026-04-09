# 🛠️ Local Development Setup — Backend

**Дата:** 10 апреля 2026  
**Статус:** ✅ Готово к использованию

---

## 🎯 Что включено

Полное локальное окружение для разработки backend:

```
✅ PostgreSQL dev (пустая база)
✅ Backend (Telegram bot) с hot reload
✅ Assistant-Infer ×3 с hot reload
✅ Support-Webhook (Stripe) с hot reload
✅ API (placeholder) с hot reload
✅ Volumes для live coding
✅ Debug logs
```

---

## 🚀 Быстрый старт

### 1. Создать dev Telegram бота

```bash
# 1. Открой Telegram → @BotFather
# 2. Отправь: /newbot
# 3. Следуй инструкциям
# 4. Сохрани токен для следующего шага
```

---

### 2. Настроить .env.local

```bash
# Скопировать example
cp .env.local.example .env.local

# Открыть в редакторе
vim .env.local  # или nano, code, etc.

# Заполнить минимум:
# - DEV_TELEGRAM_BOT_TOKEN (твой dev bot токен)
# - OPENAI_API_KEY (можно тот же что в production)
# - Остальные опционально
```

**Минимальная конфигурация:**
```bash
DEV_TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

---

### 3. Запустить dev окружение

```bash
# Собрать и запустить все сервисы
docker compose -f docker-compose.dev.yml up --build

# Или в фоне
docker compose -f docker-compose.dev.yml up -d --build

# Смотреть логи
docker compose -f docker-compose.dev.yml logs -f backend-dev
```

**Первый запуск:** ~5-10 минут (сборка образов)  
**Последующие запуски:** ~30 секунд

---

### 4. Проверить что работает

```bash
# PostgreSQL
docker exec -it vacancy-mirror-postgres-dev psql -U dev -d vacancy_mirror_dev -c "SELECT version();"

# Backend (Telegram bot)
# → Отправь /start своему dev боту в Telegram
# → Должен ответить

# API
curl http://localhost:8001/health
# → {"ok": true, ...}

# Webhook
curl http://localhost:8080/health
# → (если есть health endpoint)
```

---

## 💻 Разработка с hot reload

### Как это работает:

```
1. Изменяешь файл:
   backend/src/backend/services/telegram_bot.py

2. Сохраняешь (Cmd+S)

3. watchfiles видит изменение
   → Перезапускает процесс в контейнере
   
4. За ~2-3 секунды новый код работает!

5. Тестируешь:
   → Отправь команду dev боту
   → Видишь результат
   → Смотришь DEBUG логи в консоли
```

### Где смотреть логи:

```bash
# Все сервисы
docker compose -f docker-compose.dev.yml logs -f

# Только backend
docker compose -f docker-compose.dev.yml logs -f backend-dev

# Только assistant-infer
docker compose -f docker-compose.dev.yml logs -f assistant-infer-dev-1

# Последние 100 строк
docker compose -f docker-compose.dev.yml logs --tail 100 backend-dev
```

---

## 🗄️ Работа с базой данных

### Подключение:

```
Host: localhost
Port: 5433  (не 5432, чтобы не конфликтовать)
Database: vacancy_mirror_dev
User: dev
Password: dev123
```

### psql:

```bash
# Внутри контейнера
docker exec -it vacancy-mirror-postgres-dev psql -U dev -d vacancy_mirror_dev

# С локальной машины (если установлен psql)
psql -h localhost -p 5433 -U dev -d vacancy_mirror_dev
```

### Популярные команды:

```sql
-- Показать таблицы
\dt

-- Показать структуру таблицы
\d table_name

-- Очистить таблицу
TRUNCATE table_name CASCADE;

-- Выход
\q
```

### Сброс базы:

```bash
# Полный сброс (удалит все данные!)
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d

# База пересоздастся с нуля из init.sql
```

---

## 🐛 Debugging

### Python Debugger (pdb):

```python
# В коде добавь:
import pdb; pdb.set_trace()

# Или breakpoint (Python 3.7+):
breakpoint()

# Запусти контейнер с stdin:
docker compose -f docker-compose.dev.yml run --service-ports backend-dev
```

### VS Code Remote Containers:

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Attach to Docker",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/backend/src",
          "remoteRoot": "/app/src"
        }
      ]
    }
  ]
}
```

---

## 📊 Порты

```
Service              Local Port    Container Port
─────────────────────────────────────────────────
PostgreSQL           5433          5432
Backend (bot)        8000          8000
Assistant-infer-1    (internal)    8090
Assistant-infer-2    (internal)    8090
Assistant-infer-3    (internal)    8090
Support-Webhook      8080          8080
API                  8001          8000
```

---

## 🔧 Полезные команды

### Запуск/остановка:

```bash
# Запустить
docker compose -f docker-compose.dev.yml up

# Запустить в фоне
docker compose -f docker-compose.dev.yml up -d

# Остановить
docker compose -f docker-compose.dev.yml down

# Остановить + удалить volumes (база!)
docker compose -f docker-compose.dev.yml down -v

# Пересобрать образы
docker compose -f docker-compose.dev.yml build

# Пересобрать и запустить
docker compose -f docker-compose.dev.yml up --build
```

### Отдельные сервисы:

```bash
# Запустить только backend + postgres
docker compose -f docker-compose.dev.yml up backend-dev postgres-dev

# Перезапустить backend
docker compose -f docker-compose.dev.yml restart backend-dev

# Логи одного сервиса
docker compose -f docker-compose.dev.yml logs -f backend-dev
```

### Exec внутри контейнера:

```bash
# Bash
docker compose -f docker-compose.dev.yml exec backend-dev bash

# Python REPL
docker compose -f docker-compose.dev.yml exec backend-dev python

# Установить пакет (временно)
docker compose -f docker-compose.dev.yml exec backend-dev pip install some-package
```

---

## ⚠️ Troubleshooting

### Backend не стартует

```bash
# Проверь логи
docker compose -f docker-compose.dev.yml logs backend-dev

# Частые проблемы:
# 1. .env.local не создан → cp .env.local.example .env.local
# 2. DEV_TELEGRAM_BOT_TOKEN пустой → добавь токен
# 3. PostgreSQL не готов → подожди 10 сек
```

---

### Hot reload не работает

```bash
# Проверь что volume смонтирован
docker compose -f docker-compose.dev.yml exec backend-dev ls -la /app/src

# Проверь что watchfiles установлен
docker compose -f docker-compose.dev.yml exec backend-dev pip show watchfiles

# Пересобрать образ
docker compose -f docker-compose.dev.yml build backend-dev
```

---

### Порт занят (8000, 5433, etc.)

```bash
# Проверить что использует порт
lsof -i :8000

# Остановить production docker-compose (если запущен)
cd /path/to/production
docker compose down

# Или изменить порт в docker-compose.dev.yml
ports:
  - "9000:8000"  # вместо 8000:8000
```

---

### База не инициализируется

```bash
# Проверь что init.sql существует
ls -la infra/db/init.sql

# Полный сброс volumes
docker compose -f docker-compose.dev.yml down -v
docker volume rm vacancy-mirror-chatbot-rag_postgres-dev-data
docker compose -f docker-compose.dev.yml up -d
```

---

## 📝 Workflow разработки

### Типичный день:

```bash
# 1. Утро - запустить dev окружение
docker compose -f docker-compose.dev.yml up -d

# 2. Разработка
# - Открыть VS Code
# - Изменить backend/src/backend/services/telegram_bot.py
# - Сохранить
# - Тестировать в Telegram dev боте
# - Смотреть логи

# 3. Коммит
git add backend/src/backend/services/telegram_bot.py
git commit -m "feat: add new command"

# 4. Вечер - остановить
docker compose -f docker-compose.dev.yml down
```

### Тестирование нового функционала:

```bash
# 1. Создать feature branch
git checkout -b feature/new-command

# 2. Разработать локально с hot reload

# 3. Протестировать через dev бота

# 4. Закоммитить в dev ветку
git checkout dev
git merge feature/new-command
git push origin dev

# 5. (Опционально) Создать PR: dev → main
```

---

## 🎯 Что дальше?

### После локальной разработки:

1. ✅ Код работает локально
2. Закоммитить в `dev` ветку
3. (Опционально) Задеплоить на dev server для проверки
4. Создать Pull Request: `dev` → `main`
5. Merge → автоматический deploy на production

---

## 📚 Структура файлов

```
vacancy-mirror-chatbot-rag/
├── docker-compose.dev.yml    ← Dev окружение
├── .env.local                ← Твои dev secrets (НЕ в git!)
├── .env.local.example        ← Template
├── DEV_SETUP.md              ← Этот файл
├── backend/
│   ├── src/                  ← Volumes → hot reload!
│   └── Dockerfile
├── web/api/
│   └── Dockerfile
└── infra/db/
    └── init.sql              ← DB schema
```

---

## ✅ Checklist

- [ ] Docker установлен и запущен
- [ ] Создан dev Telegram bot (@BotFather)
- [ ] Скопирован .env.local из .env.local.example
- [ ] Заполнен DEV_TELEGRAM_BOT_TOKEN
- [ ] Заполнен OPENAI_API_KEY
- [ ] Запущен: `docker compose -f docker-compose.dev.yml up`
- [ ] Протестирован dev bot (отправь /start)
- [ ] Hot reload работает (изменил код → автоматически применилось)

---

**Готово к разработке! 🎉**

Любые вопросы → смотри Troubleshooting или спрашивай в чате.

