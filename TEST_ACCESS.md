# Инструкция по тестированию доступа к боту

## Шаг 1: Проверить текущие настройки

### На сервере выполните:
```bash
# Посмотреть переменные окружения
env | grep PAYMENT

# Или проверить в Python
python3 -c "from vechnost_bot.config import settings; print(f'PAYMENT_ENABLED: {settings.payment_enabled}'); print(f'WHITELIST: {settings.whitelisted_usernames}')"
```

### Ожидаемый результат для режима с оплатой:
```
PAYMENT_ENABLED: True
WHITELIST: ['LanaLeonovich', 'pvlmlc']
```

## Шаг 2: Включить режим оплаты

### Отредактируйте .env файл на сервере:
```bash
# Откройте .env
nano .env

# Измените:
PAYMENT_ENABLED=true

# Сохраните и перезапустите бота
```

### Или через Railway/render.com:
1. Зайдите в Dashboard
2. Variables / Environment Variables
3. Измените `PAYMENT_ENABLED` на `true`
4. Redeploy

## Шаг 3: Перезапустить бота

```bash
# Docker
docker-compose restart

# Railway/Render
# Автоматически перезапустится при изменении переменных

# Systemd
sudo systemctl restart vechnost-bot
```

## Шаг 4: Проверить логи

```bash
# Смотрим логи в реальном времени
tail -f /app/logs/bot.log

# Или Docker logs
docker logs -f vechnost-bot
```

### Что искать в логах:

#### При входе пользователя должно быть:
```
INFO: === ENTER VECHNOST DEBUG ===
INFO: User ID: 123456789
INFO: Username: testuser
INFO: PAYMENT_ENABLED: True
INFO: Subscription tier: free
INFO: Subscription active: False
INFO: Whitelisted users: ['LanaLeonovich', 'pvlmlc']
INFO: User 123456789 (@testuser) requires subscription
```

#### Если пользователь в whitelist:
```
INFO: Whitelisted user @LanaLeonovich granted access
```

#### Если пользователь оплатил:
```
INFO: Premium user 123456789 granted access
```

## Шаг 5: Тестирование разных сценариев

### Тест 1: Обычный пользователь (должен видеть экран оплаты)
1. Откройте бота с аккаунта НЕ из whitelist
2. Нажмите "ВОЙТИ В VECHNOST"
3. **Ожидается:** Экран с текстом "🔒 Премиум подписка требуется"

### Тест 2: Whitelisted пользователь (должен попасть в игру)
1. Откройте бота как @LanaLeonovich или @pvlmlc
2. Нажмите "ВОЙТИ В VECHNOST"
3. **Ожидается:** Выбор темы (✨ Знакомство, ♥️ Для Пар, 🔥 Секс, ❤️‍🔥 Провокация)

### Тест 3: Проверить что payment_enabled работает
```bash
# Временно отключить оплату
export PAYMENT_ENABLED=false
# Перезапустить бота

# Теперь ВСЕ пользователи должны попасть в игру
```

## Шаг 6: Проверка через Python REPL

На сервере:
```python
python3

from vechnost_bot.config import settings

# Проверить настройки
print("Payment enabled:", settings.payment_enabled)
print("Whitelist:", settings.whitelisted_usernames)
print("Tribute API key:", settings.tribute_api_key[:10] + "..." if settings.tribute_api_key else None)

# Проверить подписку конкретного пользователя
import asyncio
from vechnost_bot.subscription_storage import get_subscription_storage

async def check_user(user_id):
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)
    print(f"User {user_id}:")
    print(f"  Tier: {subscription.tier}")
    print(f"  Active: {subscription.is_active()}")
    print(f"  Expires: {subscription.expires_at}")

# Проверить пользователя
asyncio.run(check_user(YOUR_USER_ID))
```

## Диагностика: Почему все попадают в игру?

### Возможные причины:

#### 1. PAYMENT_ENABLED=false (самая частая причина)
```bash
# Проверить
echo $PAYMENT_ENABLED

# Если пусто или false, значит оплата отключена
```

**Решение:** Установить `PAYMENT_ENABLED=true`

#### 2. Переменная не загружается из .env
```bash
# Проверить что .env файл существует
ls -la .env

# Проверить содержимое
cat .env | grep PAYMENT_ENABLED
```

**Решение:** Убедиться что .env файл в корне проекта

#### 3. Бот не перезапущен после изменений
**Решение:** Перезапустить бота

#### 4. Username = None (пользователь не установил username в Telegram)
В логах будет:
```
INFO: Username: None
```

**Решение:** Логика правильная, такие пользователи НЕ попадут в whitelist

#### 5. Кэширование подписок в памяти
Подписка может быть закэширована с правами доступа.

**Решение:** Перезапустить бота или очистить Redis

## Быстрая диагностика (1 команда)

```bash
curl -X POST https://ваш-бот.com/health | jq
```

Или создайте debug endpoint:

```python
# Добавьте в main.py
@app.get("/debug/settings")
async def debug_settings():
    return {
        "payment_enabled": settings.payment_enabled,
        "whitelist": settings.whitelisted_usernames,
        "has_tribute_key": bool(settings.tribute_api_key)
    }
```

## Про Tribute API

Вы сказали, что Tribute дал только API key. Для полной работы нужно:

### Минимально (для создания платежей):
- ✅ `TRIBUTE_API_KEY` - есть у вас

### Для webhook (автоматическая активация):
- ❌ `TRIBUTE_WEBHOOK_SECRET` - нужен для проверки подписи
- ❌ `TRIBUTE_API_SECRET` - может не требоваться

### Без webhook:
Платежи будут работать, но:
- Пользователь должен вручную нажать "Проверить статус платежа"
- Или вы вручную активируете подписку через Python

### Решение без webhook:
```python
# Вручную активировать подписку после оплаты
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

storage = get_subscription_storage()
await storage.upgrade_subscription(
    user_id=USER_ID,  # Telegram ID пользователя
    tier=SubscriptionTier.PREMIUM,
    duration_days=30
)
```

## Контрольный чеклист

- [ ] `PAYMENT_ENABLED=true` в .env
- [ ] Бот перезапущен после изменения .env
- [ ] В логах видно "PAYMENT_ENABLED: True"
- [ ] Тестовый пользователь (не из whitelist) видит экран оплаты
- [ ] @LanaLeonovich попадает в игру
- [ ] @pvlmlc попадает в игру
- [ ] Обычный пользователь НЕ попадает в игру

## Если всё еще не работает

Отправьте мне логи с этими строками:
```
=== ENTER VECHNOST DEBUG ===
User ID: ...
Username: ...
PAYMENT_ENABLED: ...
```

И я помогу найти проблему!

