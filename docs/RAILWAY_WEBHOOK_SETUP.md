# 🚀 Настройка Webhook сервера на Railway

## 📋 Ваши URL

### Основной домен:
```
https://vechnost-bot-production.up.railway.app
```

### Webhook endpoints:

| Endpoint | URL | Описание |
|----------|-----|----------|
| Health Check | `https://vechnost-bot-production.up.railway.app/health` | Проверка работы |
| Tribute Webhook | `https://vechnost-bot-production.up.railway.app/webhooks/tribute` | Webhook для Tribute |
| Admin Sync | `https://vechnost-bot-production.up.railway.app/admin/sync-products` | Синхронизация продуктов |

---

## 🔧 Что было изменено

### 1. Создан `start_all.sh`

Скрипт запускает оба сервиса:
- Webhook сервер (FastAPI) - в фоне
- Telegram бот - в основном процессе

```bash
#!/bin/bash
PORT=${PORT:-8000}

# Start webhook server
python -m uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port $PORT &

# Start bot
python -m vechnost_bot
```

### 2. Обновлен `railway.toml`

```toml
[deploy]
startCommand = "chmod +x start_all.sh && ./start_all.sh"
```

---

## 🚀 Деплой на Railway

### Шаг 1: Закоммитить изменения

```bash
git add start_all.sh railway.toml
git commit -m "Add webhook server to Railway deployment"
git push origin feature/add_payments2
```

### Шаг 2: Задеплоить на Railway

```bash
# Автоматически задеплоится при push
# Или вручную:
railway up
```

### Шаг 3: Проверить логи

```bash
railway logs
```

Вы должны увидеть:
```
Starting webhook server on port 8000...
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
Starting Telegram bot...
Application started
```

### Шаг 4: Проверить health check

```bash
curl https://vechnost-bot-production.up.railway.app/health
```

Ожидаемый ответ:
```json
{
  "status": "ok",
  "service": "vechnost-payment-webhooks",
  "payment_enabled": "True"
}
```

---

## ⚙️ Переменные окружения

Убедитесь, что на Railway настроены:

### Обязательные:
```bash
DATABASE_URL=postgresql+asyncpg://...  # PostgreSQL URL
TELEGRAM_BOT_TOKEN=...                 # Токен бота
ENABLE_PAYMENT=True                    # Включить платежи
```

### Для webhook:
```bash
TRIBUTE_API_KEY=...                    # API ключ Tribute
TRIBUTE_BASE_URL=https://api.tribute.to
TRIBUTE_PAYMENT_URL=https://tribute.to/your_page
WEBHOOK_SECRET=...                     # Секрет для проверки подписи
```

### Опциональные:
```bash
PORT=8000                              # Порт (Railway установит автоматически)
```

---

## 🔍 Проверка работы

### 1. Health Check

```bash
curl https://vechnost-bot-production.up.railway.app/health
```

### 2. Тестовый webhook (локально)

Создайте `test_railway_webhook.py`:

```python
import httpx
import asyncio
from datetime import datetime, timedelta

async def test():
    url = "https://vechnost-bot-production.up.railway.app/webhooks/tribute"

    payload = {
        "event": "subscription.created",
        "data": {
            "id": 99999,
            "customer": {"telegram_user_id": "1115719673"},
            "period": "lifetime",
            "status": "active",
            "expires_at": None
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

asyncio.run(test())
```

Запустите:
```bash
python test_railway_webhook.py
```

### 3. Проверка в Railway

```bash
# Проверить статус
railway status

# Посмотреть логи
railway logs

# Проверить переменные
railway variables
```

---

## 🐛 Troubleshooting

### Проблема: 502 Bad Gateway

**Причина**: Сервер не запустился

**Решение**:
1. Проверьте логи: `railway logs`
2. Убедитесь, что `start_all.sh` имеет права на выполнение
3. Проверьте, что все зависимости установлены

### Проблема: Webhook возвращает 400

**Причина**: Неправильный формат payload

**Решение**:
1. Убедитесь, что `telegram_user_id` присутствует в payload
2. Проверьте структуру: `data.customer.telegram_user_id`
3. Посмотрите логи webhook: `railway logs | grep webhook`

### Проблема: Бот не отвечает

**Причина**: Webhook сервер заблокировал основной процесс

**Решение**:
1. Убедитесь, что webhook сервер запущен в фоне (`&`)
2. Проверьте, что бот запускается после webhook сервера
3. Увеличьте `sleep` в `start_all.sh` если нужно

### Проблема: База данных не обновляется

**Причина**: Неправильный `DATABASE_URL`

**Решение**:
1. Проверьте `DATABASE_URL`: `railway variables | grep DATABASE_URL`
2. Должен быть PostgreSQL URL, а не SQLite
3. Формат: `postgresql+asyncpg://user:pass@host:port/db`

---

## 📊 Мониторинг

### Проверка webhook событий

Используйте Railway PostgreSQL shell:

```bash
railway connect postgres
```

Затем в SQL консоли:

```sql
-- Последние webhook события
SELECT * FROM webhook_events
ORDER BY created_at DESC
LIMIT 10;

-- Активные подписки
SELECT u.telegram_user_id, s.status, s.period, s.expires_at
FROM subscriptions s
JOIN users u ON s.user_id = u.id
WHERE s.status = 'active';
```

### Или используйте скрипт:

```bash
railway run python check_railway_db.py
```

---

## 🎯 Настройка Tribute

1. Зайдите в [Tribute Dashboard](https://tribute.to)
2. Перейдите в Settings → Webhooks
3. Добавьте webhook URL:
   ```
   https://vechnost-bot-production.up.railway.app/webhooks/tribute
   ```
4. Скопируйте Webhook Secret
5. Добавьте на Railway:
   ```bash
   railway variables set WEBHOOK_SECRET="ваш_секрет"
   ```

---

## ✅ Checklist

- [ ] `start_all.sh` создан и закоммичен
- [ ] `railway.toml` обновлен
- [ ] Изменения запушены в git
- [ ] Railway задеплоил изменения
- [ ] Health check возвращает 200 OK
- [ ] Все переменные окружения настроены
- [ ] Webhook URL добавлен в Tribute
- [ ] WEBHOOK_SECRET настроен
- [ ] Тестовый webhook успешно обработан
- [ ] База данных обновляется корректно

---

## 📝 Следующие шаги

1. **Задеплоить изменения**:
   ```bash
   git add .
   git commit -m "Setup webhook server on Railway"
   git push
   ```

2. **Проверить деплой**:
   ```bash
   railway logs
   ```

3. **Настроить Tribute**:
   - Добавить webhook URL
   - Скопировать и добавить WEBHOOK_SECRET

4. **Протестировать**:
   - Сделать тестовую покупку
   - Проверить, что webhook обработался
   - Проверить доступ пользователя в боте

---

**🎉 Готово!** Ваш webhook сервер будет доступен по адресу:
```
https://vechnost-bot-production.up.railway.app/webhooks/tribute
```

