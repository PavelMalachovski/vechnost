# 🚀 Быстрый старт: Запуск бота с оплатой через Tribute

## 📋 Checklist перед запуском

### 1. ✅ Регистрация в Tribute
- [ ] Зарегистрироваться на https://tribute.ru/
- [ ] Пройти верификацию
- [ ] Получить API Key и API Secret
- [ ] Создать Webhook Secret

### 2. ✅ Создать тарифы в Tribute
- [ ] Создать товар "Vechnost Premium (1 месяц)" - 299₽
- [ ] Создать товар "Vechnost Premium (1 год)" - 2990₽
- [ ] Сохранить Product IDs

### 3. ✅ Настроить .env файл
```bash
# Скопировать env.example в .env
cp env.example .env

# Заполнить обязательные поля:
TELEGRAM_BOT_TOKEN=your_bot_token
REDIS_HOST=localhost
REDIS_PORT=6379
TRIBUTE_API_KEY=your_tribute_api_key
TRIBUTE_API_SECRET=your_tribute_api_secret
TRIBUTE_WEBHOOK_SECRET=your_webhook_secret
PAYMENT_ENABLED=true
AUTHOR_USERNAME=your_username
```

### 4. ✅ Запустить Redis
```bash
# Docker (рекомендуется):
docker run -d -p 6379:6379 redis:alpine

# Или установить локально
# Windows: https://redis.io/docs/install/install-redis/install-redis-on-windows/
# Linux: sudo apt install redis-server
```

### 5. ✅ Установить зависимости
```bash
pip install -r requirements.txt
# или
poetry install
```

### 6. ✅ Запустить бота локально
```bash
python -m vechnost_bot
```

### 7. ✅ Настроить Webhook URL

#### Для тестирования (ngrok):
```bash
# Установить ngrok: https://ngrok.com/download
ngrok http 8000

# Копировать URL (например, https://abc123.ngrok.io)
# В Tribute Dashboard → Webhooks → URL:
# https://abc123.ngrok.io/webhook/tribute
```

#### Для production (Railway):
```bash
railway login
railway up

# Railway даст URL: https://your-app.railway.app
# В Tribute Dashboard → Webhooks → URL:
# https://your-app.railway.app/webhook/tribute
```

### 8. ✅ Протестировать оплату
- [ ] Открыть бота в Telegram
- [ ] Нажать "Улучшить подписку"
- [ ] Выбрать тариф
- [ ] Оплатить тестовой картой: `4111 1111 1111 1111`
- [ ] Проверить что подписка активировалась

## 🎯 Структура подписок

| Функция | FREE | PREMIUM (299₽/мес) |
|---------|------|---------------------|
| Темы "Знакомство", "Для пар" | ✅ | ✅ |
| Темы "Провокация", "Секс" | ❌ | ✅ |
| Лимит вопросов в день | 10 | ∞ |
| Приоритетная поддержка | ❌ | ✅ |
| Кастомные фоны | ❌ | ✅ |

## 🔧 Быстрая диагностика

### Бот не запускается
```bash
# Проверить Redis
redis-cli ping
# Должно вернуть: PONG

# Проверить переменные окружения
python -c "from vechnost_bot.config import settings; print(f'Bot token: {settings.telegram_bot_token[:10]}...')"
```

### Webhook не работает
```bash
# Проверить что URL доступен
curl https://your-url.com/webhook/tribute
# Должно вернуть 405 Method Not Allowed (это нормально для GET)

# Проверить логи бота на ошибки
```

### Оплата не активирует подписку
```bash
# Проверить что webhook secret правильный
python -c "from vechnost_bot.config import settings; print(f'Webhook secret: {settings.tribute_webhook_secret}')"

# Проверить историю webhook в Tribute Dashboard
# Должны быть запросы со статусом 200 OK
```

## 📚 Дополнительная документация

- **Полная инструкция**: `TRIBUTE_SETUP_GUIDE.md`
- **Изменения в системе оплаты**: `PAYMENT_SIMPLIFICATION.md`
- **Примеры API**: Смотри `vechnost_bot/tribute_client.py`

## 💡 Полезные команды

```bash
# Запустить тесты
pytest tests/

# Проверить код
ruff check .

# Форматировать код
ruff format .

# Просмотреть логи (если запущено в Docker)
docker logs -f <container_id>

# Проверить Redis
redis-cli KEYS "subscription:*"
redis-cli GET "subscription:123456789"
```

## 🆘 Получить помощь

1. **Документация Tribute**: https://docs.tribute.ru/
2. **Telegram Bot API**: https://core.telegram.org/bots/api
3. **Issues**: Создайте issue в репозитории

## ✅ Готово!

После выполнения всех шагов ваш бот должен:
- ✅ Принимать платежи через Tribute
- ✅ Автоматически активировать подписки
- ✅ Ограничивать доступ для FREE пользователей
- ✅ Давать полный доступ PREMIUM пользователям

---

**Следующий шаг**: Развернуть на production сервере (Railway/Heroku/VPS)

