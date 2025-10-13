# 🧪 Тестирование Tribute Webhooks

Это руководство по тестированию webhook интеграции с Tribute.

## 📋 Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Локальное тестирование](#локальное-тестирование)
3. [Тестирование на Railway](#тестирование-на-railway)
4. [Типы событий](#типы-событий)
5. [Устранение неполадок](#устранение-неполадок)

## 🚀 Быстрый старт

### Шаг 1: Запустите webhook сервер

```bash
# В одном терминале
python -m vechnost_bot.payments.web
```

Сервер запустится на `http://localhost:8000`

### Шаг 2: Запустите тестовый скрипт

```bash
# В другом терминале
python test_webhook.py
```

### Шаг 3: Выберите тест из меню

Скрипт предложит выбрать тип события для тестирования:
- ✅ subscription.created (новая подписка)
- 🔄 subscription.renewed (продление)
- ❌ subscription.cancelled (отмена)
- 💰 payment.completed (оплата)
- ⭐ LIFETIME subscription (бессрочная)

## 🏠 Локальное тестирование

### Запуск webhook сервера

```bash
# Метод 1: Через модуль
python -m vechnost_bot.payments.web

# Метод 2: Через uvicorn напрямую
uvicorn vechnost_bot.payments.web:app --reload --port 8000
```

### Проверка работы сервера

```bash
# Health check
curl http://localhost:8000/health

# Root endpoint
curl http://localhost:8000/
```

### Отправка тестового webhook

```bash
# Используйте test_webhook.py
python test_webhook.py

# Или вручную через curl
curl -X POST http://localhost:8000/webhooks/tribute \
  -H "Content-Type: application/json" \
  -d '{
    "event": "subscription.created",
    "data": {
      "id": 12345,
      "customer": {"telegram_user_id": "1115719673"},
      "status": "active",
      "expires_at": "2025-11-13T00:00:00Z"
    }
  }'
```

## 🚂 Тестирование на Railway

### Вариант 1: Railway Shell

```bash
# Подключитесь к Railway
railway shell

# Запустите webhook сервер
python -m vechnost_bot.payments.web
```

### Вариант 2: Добавьте webhook сервис

Добавьте в ваш `railway.toml`:

```toml
[[services]]
name = "webhook-server"
command = "python -m vechnost_bot.payments.web"
```

### Получение публичного URL

1. Откройте настройки сервиса в Railway
2. Перейдите в Settings → Networking
3. Включите "Public Networking"
4. Скопируйте URL (например, `https://your-app.up.railway.app`)

### Настройка Tribute

1. Зайдите в настройки Tribute
2. Найдите раздел "Webhooks"
3. Добавьте URL: `https://your-app.up.railway.app/webhooks/tribute`
4. Добавьте WEBHOOK_SECRET если требуется

## 📡 Типы событий

### 1. subscription.created

Новая подписка создана.

```json
{
  "event": "subscription.created",
  "data": {
    "id": 12345,
    "customer": {
      "telegram_user_id": "1115719673"
    },
    "status": "active",
    "period": "1m",
    "expires_at": "2025-11-13T00:00:00Z"
  }
}
```

**Что происходит:**
- ✅ Создается/обновляется пользователь
- ✅ Создается новая подписка
- ✅ Устанавливается срок действия

### 2. subscription.renewed

Подписка продлена.

```json
{
  "event": "subscription.renewed",
  "data": {
    "id": 12345,
    "customer": {
      "telegram_user_id": "1115719673"
    },
    "status": "active",
    "expires_at": "2025-12-13T00:00:00Z"
  }
}
```

**Что происходит:**
- ✅ Обновляется дата истечения
- ✅ Статус остается active

### 3. subscription.cancelled

Подписка отменена.

```json
{
  "event": "subscription.cancelled",
  "data": {
    "id": 12345,
    "customer": {
      "telegram_user_id": "1115719673"
    },
    "status": "cancelled"
  }
}
```

**Что происходит:**
- ✅ Статус меняется на cancelled
- ✅ Пользователь теряет доступ

### 4. payment.completed

Платеж завершен.

```json
{
  "event": "payment.completed",
  "data": {
    "id": 54321,
    "customer": {
      "telegram_user_id": "1115719673"
    },
    "amount": 990,
    "status": "completed"
  }
}
```

**Что происходит:**
- ✅ Записывается платеж
- ✅ Обновляется информация о пользователе

### 5. Lifetime Subscription

Бессрочная подписка (expires_at = null).

```json
{
  "event": "subscription.created",
  "data": {
    "id": 99999,
    "customer": {
      "telegram_user_id": "1115719673"
    },
    "status": "active",
    "period": "lifetime",
    "expires_at": null
  }
}
```

**Что происходит:**
- ✅ Создается подписка без срока действия
- ✅ Пользователь получает вечный доступ

## 🔍 Проверка результатов

### После отправки webhook проверьте:

1. **Логи сервера** - должны показывать обработку события
2. **База данных** - проверьте таблицы:

```bash
# На Railway
railway run --service vechnost-db psql -c "SELECT * FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE telegram_user_id = 1115719673);"

# Или используйте check_user_payment.py
python check_user_payment.py 1115719673
```

3. **Бот** - попробуйте войти с тестовым пользователем

## 🐛 Устранение неполадок

### Сервер не запускается

**Проблема:** `ModuleNotFoundError` или ошибки импорта

**Решение:**
```bash
# Установите зависимости
pip install -e .

# Или напрямую
pip install fastapi uvicorn httpx
```

### Webhook возвращает 401 Unauthorized

**Проблема:** Неверная подпись

**Решение:**
```bash
# Проверьте WEBHOOK_SECRET в .env
echo $WEBHOOK_SECRET

# Или отключите проверку подписи в test_webhook.py
WEBHOOK_SECRET=""
```

### База данных не обновляется

**Проблема:** Таблицы не созданы

**Решение:**
```bash
# Таблицы создаются автоматически при первом обращении
# Но можно создать вручную:
python -c "from vechnost_bot.payments.database import create_tables; import asyncio; asyncio.run(create_tables())"
```

### Пользователь не найден

**Проблема:** `telegram_user_id` не указан в webhook

**Решение:**
- Убедитесь, что в payload есть `customer.telegram_user_id`
- Формат должен быть строкой: `"1115719673"`, а не числом

### Webhook обрабатывается дважды

**Проблема:** Нет идемпотентности

**Решение:**
- Система автоматически проверяет дубликаты по `webhook_events.event_id`
- Повторные webhook с тем же `event_id` игнорируются

## 📊 Мониторинг

### Просмотр всех webhook событий

```sql
SELECT * FROM webhook_events ORDER BY received_at DESC LIMIT 10;
```

### Проверка активных подписок

```sql
SELECT
  u.telegram_user_id,
  s.subscription_id,
  s.status,
  s.expires_at,
  s.period
FROM subscriptions s
JOIN users u ON s.user_id = u.id
WHERE s.status = 'active';
```

### Статистика платежей

```sql
SELECT
  COUNT(*) as total_payments,
  SUM(amount) as total_revenue,
  COUNT(DISTINCT user_id) as unique_customers
FROM payments
WHERE status = 'completed';
```

## 🎯 Рекомендации

1. **Всегда тестируйте локально** перед настройкой реального webhook
2. **Используйте `check_user_payment.py`** для проверки после webhook
3. **Проверяйте логи** в Railway для отладки
4. **Настройте WEBHOOK_SECRET** для безопасности в продакшене
5. **Мониторьте `webhook_events`** для отслеживания всех событий

## 🔗 Полезные ссылки

- [Tribute API документация](https://docs.tribute.to)
- [FastAPI документация](https://fastapi.tiangolo.com)
- [Railway документация](https://docs.railway.app)

---

**📝 Примечание:** Этот скрипт создает тестовые события для разработки. В продакшене webhooks будут приходить от Tribute автоматически.

