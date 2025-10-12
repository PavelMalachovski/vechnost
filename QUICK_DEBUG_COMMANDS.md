# Быстрая диагностика проблем с доступом

## Проверить текущие настройки (1 команда)

```bash
python3 -c "
from vechnost_bot.config import settings
print('=' * 50)
print('ТЕКУЩИЕ НАСТРОЙКИ:')
print('=' * 50)
print(f'PAYMENT_ENABLED: {settings.payment_enabled}')
print(f'Whitelist: {settings.whitelisted_usernames}')
print(f'Tribute API Key: {\"✅ Есть\" if settings.tribute_api_key else \"❌ Нет\"}')
print(f'Tribute Secret: {\"✅ Есть\" if settings.tribute_api_secret else \"❌ Нет (опционально)\"}')
print(f'Webhook Secret: {\"✅ Есть\" if settings.tribute_webhook_secret else \"❌ Нет (опционально)\"}')
print('=' * 50)
print()
print('ОЖИДАЕМОЕ ПОВЕДЕНИЕ:')
if settings.payment_enabled:
    print('✅ Режим ОПЛАТЫ включен')
    print(f'  → {settings.whitelisted_usernames} - доступ БЕЗ оплаты')
    print('  → Пользователи с Premium подпиской - доступ')
    print('  → Все остальные - экран оплаты')
else:
    print('⚠️  Режим БЕСПЛАТНОГО доступа')
    print('  → ВСЕ пользователи - полный доступ')
    print()
    print('Чтобы включить оплату:')
    print('  export PAYMENT_ENABLED=true')
    print('  или в .env: PAYMENT_ENABLED=true')
print('=' * 50)
"
```

## Включить режим оплаты

```bash
# Способ 1: Через .env файл
echo "PAYMENT_ENABLED=true" >> .env

# Способ 2: Через переменную окружения
export PAYMENT_ENABLED=true

# Перезапустить бота
docker-compose restart
# или
sudo systemctl restart vechnost-bot
```

## Посмотреть логи входа пользователей

```bash
# Показать последние попытки входа
docker logs vechnost-bot 2>&1 | grep "ENTER VECHNOST DEBUG" -A 6 | tail -50

# Или в файле
tail -100 /app/logs/bot.log | grep "ENTER VECHNOST DEBUG" -A 6
```

### Что искать:
```
=== ENTER VECHNOST DEBUG ===
User ID: 123456789
Username: testuser
PAYMENT_ENABLED: True    ← должно быть True!
Subscription tier: free
Subscription active: False
Whitelisted users: ['LanaLeonovich', 'pvlmlc']
```

## Вручную активировать подписку пользователю

```bash
python3 << 'EOF'
import asyncio
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

async def activate_premium(user_id, days=30):
    storage = get_subscription_storage()
    subscription = await storage.upgrade_subscription(
        user_id=user_id,
        tier=SubscriptionTier.PREMIUM,
        duration_days=days
    )
    print(f"✅ Пользователь {user_id} активирован на {days} дней")
    print(f"   Истекает: {subscription.expires_at}")

# ЗАМЕНИТЕ 123456789 на реальный Telegram User ID
asyncio.run(activate_premium(123456789, days=30))
EOF
```

## Проверить подписку пользователя

```bash
python3 << 'EOF'
import asyncio
from vechnost_bot.subscription_storage import get_subscription_storage

async def check_subscription(user_id):
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)

    print(f"Пользователь {user_id}:")
    print(f"  Тариф: {subscription.tier.value}")
    print(f"  Активна: {'✅ Да' if subscription.is_active() else '❌ Нет'}")
    print(f"  Подписан: {subscription.subscribed_at}")
    print(f"  Истекает: {subscription.expires_at}")
    print(f"  Дней осталось: {subscription.days_remaining() if subscription.is_active() else 0}")

# ЗАМЕНИТЕ на User ID
asyncio.run(check_subscription(123456789))
EOF
```

## Очистить подписку (сбросить к FREE)

```bash
python3 << 'EOF'
import asyncio
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier, UserSubscription

async def reset_subscription(user_id):
    storage = get_subscription_storage()
    # Создать новую FREE подписку
    subscription = UserSubscription(user_id=user_id)
    await storage.save_subscription(subscription)
    print(f"✅ Подписка пользователя {user_id} сброшена к FREE")

asyncio.run(reset_subscription(123456789))
EOF
```

## Проверить, работает ли whitelist

```bash
# Тест 1: Проверить что username в whitelist
python3 -c "
from vechnost_bot.config import settings
username = 'LanaLeonovich'  # ЗАМЕНИТЕ на тестовый username БЕЗ @
print(f'Username: @{username}')
print(f'В whitelist: {username in settings.whitelisted_usernames}')
print(f'Whitelist: {settings.whitelisted_usernames}')
"

# Тест 2: Тестовый запуск проверки доступа
python3 << 'EOF'
import asyncio
from vechnost_bot.subscription_middleware import check_premium_access

async def test_access(user_id, username):
    has_access, error = await check_premium_access(user_id, username)
    print(f"User: @{username} (ID: {user_id})")
    print(f"Доступ: {'✅ Есть' if has_access else '❌ Нет'}")
    if error:
        print(f"Ошибка: {error}")

# Тест whitelist пользователя
asyncio.run(test_access(111111, "LanaLeonovich"))
print()
# Тест обычного пользователя
asyncio.run(test_access(222222, "testuser"))
EOF
```

## Все в одном: Полная диагностика

```bash
python3 << 'EOF'
import asyncio
from vechnost_bot.config import settings
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.subscription_middleware import check_premium_access

async def full_diagnostics():
    print("=" * 60)
    print("ПОЛНАЯ ДИАГНОСТИКА СИСТЕМЫ ДОСТУПА")
    print("=" * 60)

    # 1. Настройки
    print("\n📋 НАСТРОЙКИ:")
    print(f"  PAYMENT_ENABLED: {settings.payment_enabled}")
    print(f"  Whitelist: {settings.whitelisted_usernames}")
    print(f"  Tribute API: {'✅' if settings.tribute_api_key else '❌'}")

    # 2. Ожидаемое поведение
    print("\n🎯 ОЖИДАЕМОЕ ПОВЕДЕНИЕ:")
    if settings.payment_enabled:
        print("  ✅ Режим ОПЛАТЫ:")
        print(f"    - Whitelist {settings.whitelisted_usernames}: ДОСТУП")
        print("    - Premium подписчики: ДОСТУП")
        print("    - Все остальные: ЭКРАН ОПЛАТЫ")
    else:
        print("  ⚠️  Режим БЕСПЛАТНЫЙ:")
        print("    - ВСЕ пользователи: ПОЛНЫЙ ДОСТУП")

    # 3. Тесты доступа
    print("\n🧪 ТЕСТЫ ДОСТУПА:")

    # Whitelist пользователь
    has_access, error = await check_premium_access(111111, "LanaLeonovich")
    print(f"  @LanaLeonovich: {'✅ ДОСТУП' if has_access else '❌ НЕТ ДОСТУПА'}")

    # Обычный пользователь без подписки
    has_access, error = await check_premium_access(222222, "testuser")
    print(f"  @testuser (обычный): {'❌ ДОСТУП (ОШИБКА!)' if has_access else '✅ НЕТ ДОСТУПА (правильно)'}")

    # 4. Рекомендации
    print("\n💡 РЕКОМЕНДАЦИИ:")
    if not settings.payment_enabled:
        print("  ⚠️  PAYMENT_ENABLED=false - ВСЕ имеют доступ!")
        print("      Для включения оплаты: export PAYMENT_ENABLED=true")
    else:
        print("  ✅ Настройки корректны")

    print("\n" + "=" * 60)

asyncio.run(full_diagnostics())
EOF
```

## Сохраните вывод команды и отправьте мне:

```bash
python3 << 'EOF'
import asyncio
from vechnost_bot.config import settings
from vechnost_bot.subscription_middleware import check_premium_access

async def quick_check():
    print("PAYMENT_ENABLED:", settings.payment_enabled)
    print("Whitelist:", settings.whitelisted_usernames)

    # Тест доступа
    access1, _ = await check_premium_access(111111, "LanaLeonovich")
    access2, _ = await check_premium_access(222222, "testuser")

    print("@LanaLeonovich доступ:", access1)
    print("@testuser доступ:", access2)

asyncio.run(quick_check())
EOF
```

Скопируйте вывод и отправьте мне - я сразу скажу, в чём проблема!

