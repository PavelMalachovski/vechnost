# 🔧 API примеры для тестирования платежной системы

## 📋 Примеры использования

### 1. Создание платежа

```python
from vechnost_bot.tribute_client import get_tribute_client
from vechnost_bot.payment_models import SubscriptionTier

async def create_payment_example():
    """Создать платеж для месячной подписки."""
    tribute = get_tribute_client()

    # Создаем платеж
    payment_link = await tribute.create_payment_link(
        amount=299.0,
        currency="RUB",
        description="Vechnost Premium - Месячная подписка",
        user_id=123456789,
        metadata={
            "plan_type": "monthly",
            "tier": SubscriptionTier.PREMIUM.value,
        },
        return_url="https://t.me/vechnost_bot?start=payment_success"
    )

    print(f"Payment URL: {payment_link.payment_url}")
    print(f"Payment ID: {payment_link.payment_id}")
    print(f"Expires at: {payment_link.expires_at}")

    return payment_link
```

---

### 2. Проверка статуса платежа

```python
from vechnost_bot.tribute_client import get_tribute_client

async def check_payment_example(payment_id: str):
    """Проверить статус платежа."""
    tribute = get_tribute_client()

    status = await tribute.get_payment_status(payment_id)

    print(f"Payment ID: {status.payment_id}")
    print(f"Status: {status.status}")
    print(f"Amount: {status.amount} {status.currency}")
    print(f"Customer: {status.customer_id}")
    print(f"Metadata: {status.metadata}")

    return status
```

---

### 3. Получение подписки пользователя

```python
from vechnost_bot.subscription_storage import get_subscription_storage

async def get_user_subscription_example(user_id: int):
    """Получить подписку пользователя."""
    storage = get_subscription_storage()

    subscription = await storage.get_subscription(user_id)

    print(f"User ID: {subscription.user_id}")
    print(f"Tier: {subscription.tier.value}")
    print(f"Active: {subscription.is_active()}")
    print(f"Days remaining: {subscription.days_remaining()}")
    print(f"Questions today: {subscription.questions_today}")
    print(f"Can access premium: {subscription.can_access_premium_themes()}")

    return subscription
```

---

### 4. Активация премиума

```python
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

async def activate_premium_example(user_id: int):
    """Активировать премиум подписку."""
    storage = get_subscription_storage()

    subscription = await storage.upgrade_subscription(
        user_id=user_id,
        tier=SubscriptionTier.PREMIUM,
        duration_days=30,
        payment_id="txn_123456"
    )

    print(f"✅ Premium activated!")
    print(f"Tier: {subscription.tier.value}")
    print(f"Expires: {subscription.expires_at}")
    print(f"Days remaining: {subscription.days_remaining()}")

    return subscription
```

---

### 5. Продление подписки

```python
from vechnost_bot.subscription_storage import get_subscription_storage

async def renew_subscription_example(user_id: int):
    """Продлить подписку."""
    storage = get_subscription_storage()

    subscription = await storage.renew_subscription(
        user_id=user_id,
        duration_days=30,
        payment_id="txn_renewal_123456"
    )

    print(f"✅ Subscription renewed!")
    print(f"New expiry: {subscription.expires_at}")
    print(f"Days remaining: {subscription.days_remaining()}")

    return subscription
```

---

### 6. Отмена подписки

```python
from vechnost_bot.subscription_storage import get_subscription_storage

async def cancel_subscription_example(user_id: int):
    """Отменить автопродление подписки."""
    storage = get_subscription_storage()

    subscription = await storage.cancel_subscription(user_id)

    print(f"❌ Auto-renewal cancelled")
    print(f"Auto renew: {subscription.auto_renew}")
    print(f"Subscription ID: {subscription.tribute_subscription_id}")

    return subscription
```

---

### 7. История платежей

```python
from vechnost_bot.subscription_storage import get_subscription_storage

async def get_payment_history_example(user_id: int):
    """Получить историю платежей пользователя."""
    storage = get_subscription_storage()

    payments = await storage.get_user_payments(user_id)

    print(f"Total payments: {len(payments)}")

    for payment in payments:
        print(f"\n---")
        print(f"ID: {payment.transaction_id}")
        print(f"Amount: {payment.amount} {payment.currency}")
        print(f"Status: {payment.status.value}")
        print(f"Created: {payment.created_at}")
        print(f"Completed: {payment.completed_at}")

    return payments
```

---

### 8. Проверка доступа к премиум контенту

```python
from vechnost_bot.subscription_middleware import check_premium_access
from vechnost_bot.models import Theme

async def check_access_example(user_id: int, theme: Theme):
    """Проверить доступ к теме."""
    has_access, error = await check_premium_access(user_id, theme)

    if has_access:
        print(f"✅ Access granted to {theme.value}")
    else:
        print(f"❌ Access denied: {error}")

        if error == "daily_limit_reached":
            print("💡 Upgrade to premium for unlimited access!")
        elif error == "premium_theme_required":
            print("💡 This theme is premium only!")

    return has_access
```

---

### 9. Обработка webhook

```python
from vechnost_bot.payment_webhook import process_tribute_webhook

async def handle_webhook_example(payload: dict, signature: str):
    """Обработать webhook от Tribute."""
    result = await process_tribute_webhook(payload, signature)

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")

    return result

# Пример payload
webhook_payload = {
    "event_type": "payment.completed",
    "payment_id": "pay_123456",
    "customer_id": "cust_789",
    "amount": 299.0,
    "currency": "RUB",
    "status": "completed",
    "metadata": {
        "transaction_id": "txn_abc123",
        "plan_type": "monthly"
    },
    "timestamp": "2025-10-11T12:00:00Z"
}
```

---

### 10. Статистика подписок

```python
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

async def get_subscription_stats():
    """Получить статистику подписок."""
    storage = get_subscription_storage()

    # Для примера - реальная реализация будет через Redis SCAN
    total_users = 100
    premium_users = 25

    print(f"📊 Subscription Stats")
    print(f"---")
    print(f"Total users: {total_users}")
    print(f"Premium users: {premium_users}")
    print(f"Free users: {total_users - premium_users}")
    print(f"Conversion rate: {premium_users / total_users * 100:.1f}%")
```

---

## 🧪 Полный пример: Процесс покупки

```python
import asyncio
from vechnost_bot.tribute_client import get_tribute_client
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import PaymentTransaction, PaymentStatus, SubscriptionTier

async def complete_purchase_flow(user_id: int):
    """Полный процесс покупки."""
    print("🛒 Starting purchase flow...\n")

    # 1. Проверяем текущую подписку
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)
    print(f"1️⃣ Current tier: {subscription.tier.value}")

    # 2. Создаем транзакцию
    transaction = PaymentTransaction(
        transaction_id=f"txn_{user_id}_123",
        user_id=user_id,
        amount=299.0,
        currency="RUB",
        subscription_tier=SubscriptionTier.PREMIUM,
        duration_days=30,
        status=PaymentStatus.PENDING,
    )
    await storage.save_payment(transaction)
    print(f"2️⃣ Transaction created: {transaction.transaction_id}")

    # 3. Создаем платеж в Tribute
    tribute = get_tribute_client()
    payment_link = await tribute.create_payment_link(
        amount=transaction.amount,
        currency=transaction.currency,
        description="Vechnost Premium - Monthly",
        user_id=user_id,
        metadata={"transaction_id": transaction.transaction_id}
    )
    print(f"3️⃣ Payment link: {payment_link.payment_url}")

    # 4. Пользователь оплачивает (симуляция)
    print("4️⃣ User pays... (simulated)")
    await asyncio.sleep(2)

    # 5. Webhook приходит (симуляция)
    print("5️⃣ Webhook received (simulated)")
    transaction.mark_completed()
    await storage.save_payment(transaction)

    # 6. Активируем премиум
    subscription = await storage.upgrade_subscription(
        user_id=user_id,
        tier=SubscriptionTier.PREMIUM,
        duration_days=30,
        payment_id=transaction.transaction_id
    )
    print(f"6️⃣ Premium activated!")

    # 7. Результат
    print(f"\n✅ Purchase complete!")
    print(f"Tier: {subscription.tier.value}")
    print(f"Days: {subscription.days_remaining()}")
    print(f"Expires: {subscription.expires_at}")

    return subscription

# Запуск
# asyncio.run(complete_purchase_flow(123456789))
```

---

## 🔍 Debugging

### Проверка конфигурации

```python
from vechnost_bot.config import settings

def check_config():
    """Проверить конфигурацию."""
    print("🔧 Configuration Check")
    print("---")
    print(f"Payment enabled: {settings.payment_enabled}")
    print(f"Tribute API key: {'✅' if settings.tribute_api_key else '❌'}")
    print(f"Tribute secret: {'✅' if settings.tribute_api_secret else '❌'}")
    print(f"Webhook secret: {'✅' if settings.tribute_webhook_secret else '❌'}")
    print(f"Premium channel: {settings.premium_channel_id or '❌'}")
    print(f"Invite link: {'✅' if settings.premium_channel_invite_link else '❌'}")
    print(f"Author: {settings.author_username or '❌'}")

# check_config()
```

---

## 📝 Testing Script

```python
#!/usr/bin/env python3
"""
Скрипт для тестирования платежной системы.

Usage:
    python test_payment.py create_payment 123456789
    python test_payment.py check_status pay_123456
    python test_payment.py activate_premium 123456789
"""

import asyncio
import sys
from vechnost_bot.tribute_client import get_tribute_client, cleanup_tribute_client
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.payment_models import SubscriptionTier

async def main():
    if len(sys.argv) < 2:
        print("Usage: test_payment.py <command> [args...]")
        return

    command = sys.argv[1]

    try:
        if command == "create_payment":
            user_id = int(sys.argv[2])
            tribute = get_tribute_client()
            link = await tribute.create_payment_link(
                amount=299.0,
                currency="RUB",
                description="Test Payment",
                user_id=user_id
            )
            print(f"✅ Payment created: {link.payment_url}")

        elif command == "check_status":
            payment_id = sys.argv[2]
            tribute = get_tribute_client()
            status = await tribute.get_payment_status(payment_id)
            print(f"✅ Status: {status.status}")

        elif command == "activate_premium":
            user_id = int(sys.argv[2])
            storage = get_subscription_storage()
            sub = await storage.upgrade_subscription(
                user_id=user_id,
                tier=SubscriptionTier.PREMIUM,
                duration_days=30
            )
            print(f"✅ Premium activated! Expires: {sub.expires_at}")

        elif command == "check_subscription":
            user_id = int(sys.argv[2])
            storage = get_subscription_storage()
            sub = await storage.get_subscription(user_id)
            print(f"✅ Tier: {sub.tier.value}, Active: {sub.is_active()}")

        else:
            print(f"❌ Unknown command: {command}")

    finally:
        await cleanup_tribute_client()

if __name__ == "__main__":
    asyncio.run(main())
```

---

**Готово! 🎉**

Все API примеры готовы для тестирования системы оплаты.

Запустите тесты:
```bash
python PAYMENT_API_EXAMPLES.py create_payment 123456789
```

**Сделано с ❤️ для Vechnost**

