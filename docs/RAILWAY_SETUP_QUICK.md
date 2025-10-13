# 🚀 Быстрая настройка Webhook на Railway

## 📝 Проблема

Webhook сервер не запускается из-за проблем с startCommand в Railway.

## ✅ Решение через Railway UI

### Шаг 1: Откройте Railway Dashboard

1. Зайдите на https://railway.app/project/a8fd6d12-3800-41be-806a-ee9a6c7d7ccb
2. Выберите сервис **vechnost-bot**
3. Перейдите в **Settings**

### Шаг 2: Настройте Custom Start Command

В разделе **Deploy**:

**Вариант А - Оба сервиса (РЕКОМЕНДУЕТСЯ):**
```bash
python start_services.py
```

**Вариант Б - Только webhook сервер (для тестирования):**
```bash
python -m uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port $PORT
```

**Вариант В - Только бот (текущее состояние):**
```bash
python -m vechnost_bot
```

### Шаг 3: Проверьте переменные окружения

В разделе **Variables** должны быть:

```bash
# Обязательные
DATABASE_URL=postgresql+asyncpg://postgres:...@postgres.railway.internal:5432/railway
TELEGRAM_BOT_TOKEN=...
ENABLE_PAYMENT=True

# Для webhook
TRIBUTE_API_KEY=9d8a029a-f5ca-469e-b17d-bda8bad7
TRIBUTE_BASE_URL=https://api.tribute.to
TRIBUTE_PAYMENT_URL=https://tribute.to/your_page

# Опционально
WEBHOOK_SECRET=your_secret_here
```

### Шаг 4: Redeploy

1. Нажмите **Deploy** → **Redeploy**
2. Подождите 1-2 минуты
3. Проверьте логи в разделе **Deployments**

### Шаг 5: Проверка

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

## 🐛 Альтернативное решение - Создать отдельный сервис

Если не работает, создайте **второй сервис** для webhook:

### В Railway Dashboard:

1. **New Service** → **Empty Service**
2. Имя: `webhook-server`
3. **Settings** → **Source** → Привяжите к тому же репозиторию
4. **Deploy** → **Custom Start Command**:
   ```bash
   python -m uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port $PORT
   ```
5. **Variables** → Скопируйте все переменные из `vechnost-bot`
6. **Settings** → **Networking** → **Generate Domain**

Теперь у вас будет:
- `vechnost-bot` - Telegram бот
- `webhook-server` - FastAPI webhook сервер

Webhook URL для Tribute:
```
https://webhook-server-production.up.railway.app/webhooks/tribute
```

---

## 📋 Для Tribute

После успешного деплоя:

1. Откройте Tribute Dashboard
2. Настройки → Webhooks
3. URL: `https://vechnost-bot-production.up.railway.app/webhooks/tribute`
4. Нажмите "Test Webhook"
5. Должен вернуть 200 OK

---

## ✅ Checklist

- [ ] Custom Start Command настроен
- [ ] Все переменные окружения добавлены
- [ ] TRIBUTE_API_KEY = `9d8a029a-f5ca-469e-b17d-bda8bad7`
- [ ] Сервис задеплоен (Redeploy)
- [ ] Health check возвращает 200 OK
- [ ] Webhook URL добавлен в Tribute
- [ ] Test Webhook в Tribute успешен

---

## 🔧 Текущие файлы

Созданы следующие файлы для деплоя:

1. `start_services.py` - Python скрипт для запуска обоих сервисов
2. `railway.toml` - Конфигурация Railway (возможно не работает)
3. `Procfile` - Альтернативная конфигурация

**Рекомендация**: Используйте UI Railway для настройки Custom Start Command вместо файлов конфигурации.

