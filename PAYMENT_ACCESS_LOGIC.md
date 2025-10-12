# Логика доступа к игре с оплатой

## Обзор изменений

Система переведена на **полную модель оплаты**:
- ❌ Убраны дневные лимиты (10 вопросов в день)
- ✅ Доступ только по подписке
- ✅ Whitelist для тестовых пользователей
- ✅ Интеграция с Tribute для обработки платежей

---

## Логика доступа

### Режим `payment_enabled = FALSE`
**Игра доступна всем пользователям бесплатно**

```
Любой пользователь → Полный доступ к игре
```

### Режим `payment_enabled = TRUE`
**Игра только по подписке + whitelist**

```
1. Whitelisted пользователи (@LanaLeonovich, @pvlmlc) → Полный доступ
2. Премиум подписчики (оплатили через Tribute) → Полный доступ
3. Все остальные → Экран оплаты
```

---

## Конфигурация

### Переменные окружения (.env)

```bash
# Включение/выключение платежей
PAYMENT_ENABLED=true

# Tribute API ключи
TRIBUTE_API_KEY=your_api_key
TRIBUTE_API_SECRET=your_api_secret
TRIBUTE_WEBHOOK_SECRET=your_webhook_secret
TRIBUTE_BASE_URL=https://api.tribute.ru

# Whitelist пользователей (username без @)
# По умолчанию: LanaLeonovich, pvlmlc
```

### Whitelist пользователей

Whitelist настраивается в `vechnost_bot/config.py`:

```python
whitelisted_usernames: list[str] = Field(
    default=["LanaLeonovich", "pvlmlc"],
    description="Usernames allowed to access without payment for testing"
)
```

**Важно**: Указывайте username БЕЗ символа `@`

---

## Как работает оплата

### 1. Пользователь нажимает "ВОЙТИ В VECHNOST"

**Проверка доступа:**
```python
if payment_enabled:
    if username in whitelist:
        ✅ Доступ разрешен
    elif has_premium_subscription:
        ✅ Доступ разрешен
    else:
        ❌ Показать экран оплаты
else:
    ✅ Доступ разрешен для всех
```

### 2. Пользователь выбирает план и оплачивает

1. Создается `PaymentTransaction` со статусом `PENDING`
2. Генерируется ссылка на оплату через Tribute API
3. Пользователь переходит на страницу оплаты
4. После оплаты Tribute отправляет webhook `payment.completed`

### 3. Webhook обработка (автоматически)

**Endpoint:** `POST /webhook/tribute`

```python
# 1. Проверка подписи webhook
if not verify_signature(payload, signature):
    return error

# 2. Обработка события payment.completed
payment = get_payment(transaction_id)
payment.mark_completed()

# 3. Активация подписки
subscription = upgrade_subscription(
    user_id=payment.user_id,
    tier=SubscriptionTier.PREMIUM,
    duration_days=payment.duration_days
)

# 4. Пользователь получает доступ
```

### 4. Проверка при каждом действии

При выборе темы/вопроса система проверяет:

```python
async def check_premium_access(user_id, username):
    if not payment_enabled:
        return True  # Всем доступ

    if username in whitelist:
        return True  # Whitelist

    subscription = get_subscription(user_id)
    if subscription.is_active() and subscription.tier == PREMIUM:
        return True  # Активная подписка

    return False  # Нет доступа
```

---

## Тарифные планы

### Месячный план
- **Цена:** 299 ₽
- **Срок:** 30 дней
- **Доступ:** Все темы и вопросы

### Годовой план
- **Цена:** 2990 ₽ (скидка 17%)
- **Срок:** 365 дней
- **Доступ:** Все темы и вопросы

---

## Структура подписки

```python
class UserSubscription:
    user_id: int
    tier: SubscriptionTier  # FREE | PREMIUM
    subscribed_at: datetime | None
    expires_at: datetime | None
    auto_renew: bool

    def is_active(self) -> bool:
        """Проверка активности подписки"""
        if self.tier == FREE:
            return False
        if not self.expires_at:
            return False
        return datetime.utcnow() < self.expires_at
```

---

## Тестирование

### Локальное тестирование

1. **Тестовый пользователь (whitelist):**
   ```bash
   # В .env
   PAYMENT_ENABLED=true

   # Войдите как @LanaLeonovich или @pvlmlc
   # Доступ будет разрешен без оплаты
   ```

2. **Тестовый пользователь (требуется оплата):**
   ```bash
   # Войдите с любым другим username
   # Увидите экран оплаты
   ```

3. **Режим без оплаты:**
   ```bash
   # В .env
   PAYMENT_ENABLED=false

   # Все пользователи получат доступ
   ```

### Проверка webhook

Используйте ngrok для локального тестирования:

```bash
ngrok http 8000

# В Tribute Dashboard укажите:
# Webhook URL: https://your-ngrok-url/webhook/tribute
```

---

## Мониторинг

### Логи доступа

```python
# Whitelist пользователь
INFO: Whitelisted user @LanaLeonovich granted access

# Премиум пользователь
INFO: Premium user 123456789 granted access

# Требуется подписка
INFO: User 123456789 (@username) requires subscription
```

### Логи платежей

```python
# Создание платежа
INFO: Created payment link: txn_123456789_abcd1234

# Webhook получен
INFO: Payment txn_123456789_abcd1234 completed for user 123456789

# Подписка активирована
INFO: Upgraded user 123456789 to premium
```

---

## FAQ

### Как добавить нового тестового пользователя?

Отредактируйте `vechnost_bot/config.py`:

```python
whitelisted_usernames: list[str] = Field(
    default=["LanaLeonovich", "pvlmlc", "new_tester"],
    ...
)
```

Или через переменную окружения (если добавите поддержку):

```bash
WHITELISTED_USERNAMES=LanaLeonovich,pvlmlc,new_tester
```

### Как вручную активировать подписку?

```python
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

storage = get_subscription_storage()
await storage.upgrade_subscription(
    user_id=123456789,
    tier=SubscriptionTier.PREMIUM,
    duration_days=30
)
```

### Что делать, если webhook не работает?

1. Проверьте, что `TRIBUTE_WEBHOOK_SECRET` настроен
2. Проверьте логи на наличие `Invalid webhook signature`
3. Используйте кнопку "Проверить статус платежа" в боте
4. Вручную проверьте статус через Tribute API

### Как отключить платежи на production?

```bash
# В .env
PAYMENT_ENABLED=false
```

**Внимание:** Все пользователи получат доступ!

---

## Безопасность

### Проверка подписи webhook

Все webhook от Tribute проверяются с помощью HMAC SHA256:

```python
signature = hmac.new(
    TRIBUTE_WEBHOOK_SECRET.encode(),
    payload.encode(),
    hashlib.sha256
).hexdigest()

if signature != received_signature:
    reject()
```

### Хранение данных

- Подписки хранятся в Redis с TTL
- Платежи хранятся с увеличенным TTL (48x)
- Sensitive данные не логируются

---

## Миграция со старой системы

### Что удалено:

- ❌ `daily_question_count` - счетчик вопросов
- ❌ `daily_limit_prompt` - текст о лимите
- ❌ `can_ask_question_today()` - проверка дневного лимита
- ❌ Проверка на "премиум темы" (Sex, Provocation)

### Что добавлено:

- ✅ Whitelist пользователей
- ✅ `premium_required` - единый текст для подписки
- ✅ Новая логика в `check_premium_access()`
- ✅ Полная интеграция с Tribute

---

## Контакты

При проблемах с платежами:
- Проверьте логи: `/app/logs/`
- Tribute Dashboard: https://dashboard.tribute.ru
- Поддержка Tribute: support@tribute.ru

