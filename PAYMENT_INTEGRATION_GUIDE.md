# 💳 Руководство по интеграции платежной системы Vechnost

## 📋 Обзор

Vechnost бот теперь поддерживает систему подписок с интеграцией платежного шлюза **Tribute**. Система включает:

- ✅ Бесплатный и премиум тарифы
- ✅ Интеграция с Tribute API
- ✅ Webhook для автоматической обработки платежей
- ✅ Красивый welcome screen (как у ХЛБ)
- ✅ Премиум телеграм канал
- ✅ Разграничение доступа к контенту
- ✅ Связь с автором

---

## 🎯 Архитектура системы

### Компоненты

```
vechnost_bot/
├── payment_models.py          # Модели подписок и платежей
├── payment_keyboards.py       # Клавиатуры для платежной системы
├── payment_handlers.py        # Обработчики платежных действий
├── subscription_storage.py    # Хранилище подписок
├── subscription_middleware.py # Middleware для проверки доступа
├── tribute_client.py          # Клиент Tribute API
└── payment_webhook.py         # Webhook обработчик
```

### Тарифы

#### 🆓 Бесплатный тариф
- Базовые темы: Знакомство, Для Пар
- Лимит: 10 вопросов в день
- Без доступа к премиум каналу

#### ⭐ Премиум тариф
- **299 ₽/месяц** или **2990 ₽/год** (скидка 17%)
- Все темы без ограничений (включая Секс и Провокация)
- Неограниченные вопросы
- Доступ к эксклюзивному премиум каналу
- Приоритетная поддержка
- Персональные фоны

---

## 🔧 Настройка

### 1. Регистрация в Tribute

1. Зарегистрируйтесь на [Tribute](https://tribute.ru/)
2. Создайте продукт для подписки
3. Получите API ключи в личном кабинете:
   - `API Key`
   - `API Secret`
   - `Webhook Secret`

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
# Tribute Payment Configuration
TRIBUTE_API_KEY=your_tribute_api_key_here
TRIBUTE_API_SECRET=your_tribute_api_secret_here
TRIBUTE_WEBHOOK_SECRET=your_webhook_secret_here
TRIBUTE_BASE_URL=https://api.tribute.ru

# Premium Channel Configuration
PREMIUM_CHANNEL_ID=@vechnost_premium
PREMIUM_CHANNEL_INVITE_LINK=https://t.me/+your_invite_link

# Contact Configuration
SUPPORT_USERNAME=@vechnost_support
AUTHOR_USERNAME=@your_username

# Enable Payments
PAYMENT_ENABLED=true
```

### 3. Создание премиум канала

1. Создайте приватный телеграм канал
2. Добавьте бота как администратора
3. Создайте invite link
4. Укажите ссылку в `PREMIUM_CHANNEL_INVITE_LINK`

### 4. Настройка Webhook в Tribute

Настройте webhook URL в Tribute:

```
https://your-domain.com/webhook/tribute
```

**Важно**: Укажите `TRIBUTE_WEBHOOK_SECRET` для проверки подписи.

---

## 🚀 Использование

### Для пользователей

1. **Запуск бота**: `/start`
2. **Выбор языка**: Русский/English/Čeština
3. **Welcome screen** с кнопками:
   - 🏠 ВОЙТИ В VECHNOST
   - 💡 ЧТО ТЕБЯ ЖДЁТ ВНУТРИ?
   - ❤️ ПОЧЕМУ VECHNOST ПОМОЖЕТ?
   - ⭐ ОТЗЫВЫ О VECHNOST
   - 🛡️ ГАРАНТИЯ
   - 💬 Связаться с автором

4. **Получение премиума**:
   - Нажмите "ВОЙТИ В VECHNOST"
   - Выберите план подписки
   - Оплатите через Tribute
   - Проверьте статус оплаты

### Для разработчиков

#### Проверка подписки в коде

```python
from .subscription_middleware import check_and_enforce_subscription

# В вашем handler
has_access = await check_and_enforce_subscription(query, session, theme)
if not has_access:
    return  # Пользователю показано сообщение об обновлении
```

#### Получение подписки пользователя

```python
from .subscription_storage import get_subscription_storage

storage = get_subscription_storage()
subscription = await storage.get_subscription(user_id)

if subscription.is_active():
    print(f"Premium active, {subscription.days_remaining()} days left")
```

#### Создание платежа

```python
from .tribute_client import get_tribute_client

tribute = get_tribute_client()
payment_link = await tribute.create_payment_link(
    amount=299.0,
    currency="RUB",
    description="Vechnost Premium - Месячная подписка",
    user_id=user_id,
    metadata={"plan": "monthly"}
)

print(f"Payment URL: {payment_link.payment_url}")
```

---

## 🔒 Безопасность

### Проверка webhook подписи

```python
from .tribute_client import get_tribute_client

tribute = get_tribute_client()

# Проверка подписи из header
is_valid = tribute.verify_webhook_signature(
    payload=request_body,
    signature=request.headers.get("X-Tribute-Signature")
)

if not is_valid:
    return {"error": "Invalid signature"}, 403
```

### Защита от несанкционированного доступа

- Все премиум темы проверяются через middleware
- Лимиты для бесплатных пользователей
- Автоматическое отключение истекших подписок

---

## 📊 Мониторинг

### События логирования

Система логирует следующие события:

```python
- payment_created        # Платёж создан
- payment_completed      # Платёж успешно завершён
- payment_failed         # Платёж не прошёл
- subscription_upgraded  # Подписка улучшена
- subscription_renewed   # Подписка продлена
- subscription_cancelled # Подписка отменена
```

### Просмотр статистики

```python
from .subscription_storage import get_subscription_storage

storage = get_subscription_storage()

# Получить все платежи пользователя
payments = await storage.get_user_payments(user_id)

for payment in payments:
    print(f"Payment: {payment.amount} RUB - {payment.status}")
```

---

## 🧪 Тестирование

### Тестовые платежи

Tribute предоставляет тестовый режим. Установите:

```bash
TRIBUTE_BASE_URL=https://sandbox.tribute.ru
```

### Отключение платежей для разработки

```bash
PAYMENT_ENABLED=false
```

При `PAYMENT_ENABLED=false` все пользователи получают полный доступ.

---

## 🎨 Кастомизация

### Изменение цен

Отредактируйте `vechnost_bot/payment_models.py`:

```python
SubscriptionPlan(
    tier=SubscriptionTier.PREMIUM,
    name="Премиум",
    description="⭐ Полный доступ ко всем темам + эксклюзивный канал",
    price_monthly=299.0,  # Измените здесь
    price_yearly=2990.0,  # Измените здесь
    # ...
)
```

### Изменение текстов

Отредактируйте `data/translations_ru.yaml`:

```yaml
welcome:
  enter_vechnost: "ВОЙТИ В VECHNOST ←"
  # Измените тексты здесь
```

### Добавление новых функций премиума

Отредактируйте `payment_models.py`:

```python
class SubscriptionFeatures(BaseModel):
    basic_themes: bool = True
    premium_themes: bool = False

    # Добавьте новые функции
    custom_questions: bool = False
    ai_suggestions: bool = False
```

---

## 🐛 Решение проблем

### Платежи не обрабатываются

1. Проверьте webhook URL в Tribute
2. Убедитесь, что `TRIBUTE_WEBHOOK_SECRET` совпадает
3. Проверьте логи: `grep "webhook" logs/bot.log`

### Пользователи не получают доступ

1. Проверьте статус подписки: `redis-cli GET subscription:{user_id}`
2. Убедитесь, что `PAYMENT_ENABLED=true`
3. Проверьте даты подписки

### Ошибки Tribute API

```bash
# Проверьте API keys
echo $TRIBUTE_API_KEY

# Тестовый запрос
curl -H "Authorization: Bearer $TRIBUTE_API_KEY" \
     https://api.tribute.ru/v1/payments
```

---

## 📞 Поддержка

- 📧 Email: support@vechnost.app
- 💬 Telegram: @vechnost_support
- 🐛 Issues: [GitHub Issues](https://github.com/your-repo/issues)

---

## 📝 Changelog

### v2.0.0 (2025-10-11)
- ✅ Добавлена интеграция с Tribute
- ✅ Система подписок Free/Premium
- ✅ Welcome screen как у ХЛБ
- ✅ Премиум телеграм канал
- ✅ Webhook обработка платежей
- ✅ Разграничение доступа к контенту

---

## 📄 Лицензия

MIT License - см. LICENSE файл

---

**Сделано с ❤️ для Vechnost**

