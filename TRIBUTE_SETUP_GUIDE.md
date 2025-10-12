# 🔧 Настройка оплаты через Tribute для Telegram бота

## Шаг 1: Регистрация в Tribute

1. **Зайдите на сайт Tribute**: https://tribute.ru/
2. **Зарегистрируйтесь** как продавец/предприниматель
3. **Пройдите верификацию** (загрузите документы, подтвердите ИП/ООО)
4. **Дождитесь одобрения** аккаунта (обычно 1-3 дня)

## Шаг 2: Получение API ключей

После одобрения аккаунта:

1. Зайдите в **Панель управления Tribute**
2. Перейдите в раздел **"Настройки"** → **"API"**
3. Создайте новый **API ключ**:
   - Нажмите "Создать ключ"
   - Выберите права: `payments.read`, `payments.write`, `subscriptions.read`, `subscriptions.write`
   - Сохраните **API Key** и **API Secret** в надежное место

4. В разделе **"Webhooks"** создайте webhook:
   - URL: `https://ваш-домен.com/webhook/tribute`
   - Секрет webhook: сгенерируйте случайную строку (например, `openssl rand -hex 32`)
   - События: выберите `payment.succeeded`, `subscription.activated`, `subscription.renewed`, `subscription.canceled`

## Шаг 3: Создание товаров/подписок в Tribute

1. В панели Tribute перейдите в **"Товары"** → **"Добавить товар"**
2. Создайте **два тарифа**:

### Тариф "Месячная подписка"
- **Название**: Vechnost Premium (1 месяц)
- **Цена**: 299 ₽
- **Тип**: Одноразовая покупка или Подписка
- **Описание**: Доступ ко всем темам и вопросам на 1 месяц
- **ID товара**: запомните/скопируйте (например, `prod_monthly_299`)

### Тариф "Годовая подписка"
- **Название**: Vechnost Premium (1 год)
- **Цена**: 2990 ₽
- **Тип**: Одноразовая покупка или Подписка
- **Описание**: Доступ ко всем темам и вопросам на 1 год (экономия 33%)
- **ID товара**: запомните/скопируйте (например, `prod_yearly_2990`)

## Шаг 4: Настройка окружения бота

Создайте файл `.env` на основе `env.example`:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# Tribute API
TRIBUTE_API_KEY=your_tribute_api_key
TRIBUTE_API_SECRET=your_tribute_api_secret
TRIBUTE_WEBHOOK_SECRET=your_generated_webhook_secret
TRIBUTE_BASE_URL=https://api.tribute.ru

# Payment Configuration
PAYMENT_ENABLED=true

# Support
AUTHOR_USERNAME=your_telegram_username
SUPPORT_USERNAME=your_support_username

# Monitoring (опционально)
SENTRY_DSN=your_sentry_dsn
```

## Шаг 5: Настройка webhook URL

Ваш бот должен быть доступен из интернета для получения webhook от Tribute.

### Вариант A: Использование ngrok для тестирования

```bash
# Установите ngrok
ngrok http 8000

# Скопируйте URL (например, https://abc123.ngrok.io)
# Используйте его как webhook URL: https://abc123.ngrok.io/webhook/tribute
```

### Вариант B: Развертывание на сервере

1. **Railway.app** (рекомендуется):
   ```bash
   railway login
   railway up
   # Railway автоматически даст вам URL
   ```

2. **Heroku**:
   ```bash
   heroku create your-app-name
   git push heroku main
   # URL: https://your-app-name.herokuapp.com
   ```

3. **VPS/Dedicated Server**:
   - Настройте Nginx/Apache как reverse proxy
   - Получите SSL сертификат (Let's Encrypt)
   - URL: https://yourdomain.com

## Шаг 6: Обновление Tribute с webhook URL

1. Вернитесь в **Tribute Dashboard** → **"Webhooks"**
2. Отредактируйте ваш webhook
3. Установите **URL**: `https://your-actual-domain.com/webhook/tribute`
4. Убедитесь что выбраны события:
   - `payment.succeeded`
   - `subscription.activated`
   - `subscription.renewed`
   - `subscription.canceled`
5. Сохраните

## Шаг 7: Обновление кода для работы с реальными Product ID

Откройте `vechnost_bot/tribute_client.py` и обновите методы для использования реальных Product ID из Tribute:

```python
# В методе create_payment_link или create_subscription
# Вместо захардкоженных значений используйте реальные product_id
payload = {
    "product_id": "prod_monthly_299",  # ← Ваш реальный ID из Tribute
    "success_url": success_url,
    "fail_url": fail_url,
    "webhook_url": webhook_url,
    "metadata": metadata,
}
```

## Шаг 8: Тестирование оплаты

1. **Запустите бота**:
   ```bash
   python -m vechnost_bot
   ```

2. **Откройте бота в Telegram**
3. **Нажмите "Улучшить подписку"**
4. **Выберите тариф** (месячный/годовой)
5. **Перейдите по ссылке оплаты**

### Тестовые карты Tribute:
- **Успешная оплата**: `4111 1111 1111 1111`
- **Отклоненная оплата**: `4242 4242 4242 4242`
- CVV: любые 3 цифры
- Срок: любая будущая дата

## Шаг 9: Проверка webhook

После тестовой оплаты проверьте логи бота:

```bash
# Должны увидеть:
[INFO] Received Tribute webhook event
[INFO] Tribute webhook event: payment.succeeded
[INFO] User 123456789 subscription updated to PREMIUM via webhook
```

Проверьте в Tribute Dashboard → **"Webhooks"** → **"История"**:
- Должны быть записи об отправленных webhook
- Статус: 200 OK

## Шаг 10: Мониторинг

1. **Логи бота**: регулярно проверяйте на ошибки
2. **Tribute Dashboard**: отслеживайте платежи и подписки
3. **Redis**: убедитесь что подписки сохраняются корректно

## Troubleshooting

### Webhook не приходят
- Убедитесь что URL доступен из интернета
- Проверьте HTTPS (Tribute требует SSL)
- Проверьте что webhook secret правильный

### Оплата не активирует подписку
- Проверьте логи бота на ошибки
- Убедитесь что Redis работает
- Проверьте metadata в платеже (должен быть user_id)

### Ошибка "Invalid signature"
- Проверьте что TRIBUTE_WEBHOOK_SECRET совпадает с секретом в Tribute

## Полезные ссылки

- **Tribute API Docs**: https://docs.tribute.ru/
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **Python Telegram Bot Library**: https://python-telegram-bot.org/

---

✅ **Готово!** Теперь ваш бот принимает платежи через Tribute.


