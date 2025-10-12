#!/usr/bin/env python3
"""
Диагностический скрипт для проверки настроек доступа к боту.
Запуск: python3 check_payment_settings.py
"""

import asyncio
import sys
from pathlib import Path

# Добавить путь к модулям бота
sys.path.insert(0, str(Path(__file__).parent))

from vechnost_bot.config import settings
from vechnost_bot.subscription_storage import get_subscription_storage
from vechnost_bot.subscription_middleware import check_premium_access


def print_header(text: str):
    """Красивый заголовок."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_status(label: str, value: any, ok: bool = True):
    """Вывод статуса с эмодзи."""
    emoji = "✅" if ok else "❌"
    print(f"  {emoji} {label}: {value}")


async def check_user_subscription(user_id: int, label: str = "Пользователь"):
    """Проверить подписку конкретного пользователя."""
    try:
        storage = get_subscription_storage()
        subscription = await storage.get_subscription(user_id)

        print(f"\n  {label} (ID: {user_id}):")
        print(f"    Тариф: {subscription.tier.value}")
        print(f"    Активна: {'✅ Да' if subscription.is_active() else '❌ Нет'}")

        if subscription.is_active():
            days = subscription.days_remaining()
            print(f"    Осталось дней: {days}")
            print(f"    Истекает: {subscription.expires_at}")
    except Exception as e:
        print(f"    ❌ Ошибка: {e}")


async def test_access_scenarios():
    """Тестировать разные сценарии доступа."""
    print_header("ТЕСТЫ ДОСТУПА")

    # Тест 1: Whitelist пользователь
    print("\n  Тест 1: Whitelist пользователь (@LanaLeonovich)")
    has_access, error = await check_premium_access(
        user_id=111111,
        username="LanaLeonovich"
    )
    if has_access:
        print_status("Результат", "ДОСТУП РАЗРЕШЕН", ok=True)
    else:
        print_status("Результат", f"ДОСТУП ЗАПРЕЩЕН ({error})", ok=False)
        print("    ⚠️  ОШИБКА: Whitelist пользователь должен иметь доступ!")

    # Тест 2: Второй whitelist пользователь
    print("\n  Тест 2: Whitelist пользователь (@pvlmlc)")
    has_access, error = await check_premium_access(
        user_id=222222,
        username="pvlmlc"
    )
    if has_access:
        print_status("Результат", "ДОСТУП РАЗРЕШЕН", ok=True)
    else:
        print_status("Результат", f"ДОСТУП ЗАПРЕЩЕН ({error})", ok=False)
        print("    ⚠️  ОШИБКА: Whitelist пользователь должен иметь доступ!")

    # Тест 3: Обычный пользователь (без подписки)
    print("\n  Тест 3: Обычный пользователь (@testuser)")
    has_access, error = await check_premium_access(
        user_id=333333,
        username="testuser"
    )
    if settings.payment_enabled:
        if has_access:
            print_status("Результат", "ДОСТУП РАЗРЕШЕН", ok=False)
            print("    ⚠️  ОШИБКА: Обычный пользователь НЕ должен иметь доступ!")
        else:
            print_status("Результат", f"ДОСТУП ЗАПРЕЩЕН ({error})", ok=True)
            print("    ✅ Правильно: требуется подписка")
    else:
        if has_access:
            print_status("Результат", "ДОСТУП РАЗРЕШЕН", ok=True)
            print("    ℹ️  PAYMENT_ENABLED=false - все имеют доступ")
        else:
            print_status("Результат", f"ДОСТУП ЗАПРЕЩЕН ({error})", ok=False)
            print("    ⚠️  ОШИБКА: При PAYMENT_ENABLED=false все должны иметь доступ!")

    # Тест 4: Пользователь без username
    print("\n  Тест 4: Пользователь без username (None)")
    has_access, error = await check_premium_access(
        user_id=444444,
        username=None
    )
    if settings.payment_enabled:
        if has_access:
            print_status("Результат", "ДОСТУП РАЗРЕШЕН", ok=False)
            print("    ⚠️  ОШИБКА: Пользователь без username не в whitelist!")
        else:
            print_status("Результат", f"ДОСТУП ЗАПРЕЩЕН ({error})", ok=True)
            print("    ✅ Правильно: требуется подписка")


async def main():
    """Главная функция диагностики."""

    # 1. Проверка настроек
    print_header("НАСТРОЙКИ СИСТЕМЫ")

    print_status("PAYMENT_ENABLED", settings.payment_enabled)
    print_status("Whitelist", settings.whitelisted_usernames)
    print_status(
        "Tribute API Key",
        "✅ Установлен" if settings.tribute_api_key else "❌ Отсутствует",
        ok=bool(settings.tribute_api_key)
    )
    print_status(
        "Tribute API Secret",
        "✅ Установлен (для webhook)" if settings.tribute_api_secret else "❌ Отсутствует (опционально)",
        ok=True  # не критично
    )
    print_status(
        "Webhook Secret",
        "✅ Установлен (для webhook)" if settings.tribute_webhook_secret else "❌ Отсутствует (опционально)",
        ok=True  # не критично
    )

    # 2. Ожидаемое поведение
    print_header("ОЖИДАЕМОЕ ПОВЕДЕНИЕ")

    if settings.payment_enabled:
        print("\n  🔒 РЕЖИМ ОПЛАТЫ ВКЛЮЧЕН")
        print(f"    • Whitelist {settings.whitelisted_usernames}: ДОСТУП БЕЗ ОПЛАТЫ")
        print("    • Пользователи с Premium подпиской: ДОСТУП")
        print("    • Все остальные: ЭКРАН ОПЛАТЫ")
    else:
        print("\n  🆓 РЕЖИМ БЕСПЛАТНОГО ДОСТУПА")
        print("    • ВСЕ пользователи: ПОЛНЫЙ ДОСТУП")
        print()
        print("  ⚠️  ВНИМАНИЕ: Все попадают в игру без оплаты!")
        print("      Для включения оплаты:")
        print("        1. Установите в .env: PAYMENT_ENABLED=true")
        print("        2. Или: export PAYMENT_ENABLED=true")
        print("        3. Перезапустите бота")

    # 3. Тесты доступа
    await test_access_scenarios()

    # 4. Рекомендации
    print_header("РЕКОМЕНДАЦИИ")

    issues_found = False

    if not settings.payment_enabled:
        print("\n  ⚠️  КРИТИЧНО: PAYMENT_ENABLED=false")
        print("      → Все пользователи имеют доступ без оплаты!")
        print("      → Установите PAYMENT_ENABLED=true для включения оплаты")
        issues_found = True

    if not settings.tribute_api_key:
        print("\n  ⚠️  КРИТИЧНО: Отсутствует TRIBUTE_API_KEY")
        print("      → Платежи не будут работать!")
        print("      → Получите API ключ от Tribute и добавьте в .env")
        issues_found = True

    if not settings.tribute_webhook_secret and settings.payment_enabled:
        print("\n  ℹ️  ИНФОРМАЦИЯ: Отсутствует TRIBUTE_WEBHOOK_SECRET")
        print("      → Автоматическая активация после оплаты не работает")
        print("      → Пользователи должны нажимать 'Проверить статус платежа'")
        print("      → Это не критично, но менее удобно")

    if not issues_found:
        print("\n  ✅ Все настройки корректны!")
        print("      Система должна работать правильно.")

    # 5. Команды для исправления
    if not settings.payment_enabled or not settings.tribute_api_key:
        print_header("КОМАНДЫ ДЛЯ ИСПРАВЛЕНИЯ")

        if not settings.payment_enabled:
            print("\n  Включить режим оплаты:")
            print("    echo 'PAYMENT_ENABLED=true' >> .env")
            print("    docker-compose restart")

        if not settings.tribute_api_key:
            print("\n  Добавить Tribute API ключ:")
            print("    echo 'TRIBUTE_API_KEY=your_key_here' >> .env")
            print("    docker-compose restart")

    print("\n" + "=" * 60)

    if not issues_found and settings.payment_enabled:
        print("\n✅ СИСТЕМА НАСТРОЕНА ПРАВИЛЬНО")
        print(f"   → @{settings.whitelisted_usernames[0]} и @{settings.whitelisted_usernames[1]} имеют доступ")
        print("   → Остальные пользователи видят экран оплаты")
    elif not settings.payment_enabled:
        print("\n⚠️  ВСЕ ПОЛЬЗОВАТЕЛИ ИМЕЮТ ДОСТУП БЕЗ ОПЛАТЫ")
        print("   → Установите PAYMENT_ENABLED=true для исправления")
    else:
        print("\n⚠️  НАЙДЕНЫ ПРОБЛЕМЫ - см. выше")

    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

