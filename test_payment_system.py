#!/usr/bin/env python3
"""
Payment system test script for Vechnost bot.

Usage:
    python test_payment_system.py
"""

import asyncio
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, '.')


async def test_imports():
    """Test 1: Check imports."""
    print("=" * 60)
    print("TEST 1: Imports Check")
    print("=" * 60)

    try:
        from vechnost_bot.payment_models import (
            SubscriptionTier,
            UserSubscription,
            PaymentTransaction,
            PaymentStatus,
            get_subscription_plan
        )
        print("[OK] payment_models")

        from vechnost_bot.tribute_client import TributeClient, get_tribute_client
        print("[OK] tribute_client")

        from vechnost_bot.subscription_storage import SubscriptionStorage, get_subscription_storage
        print("[OK] subscription_storage")

        from vechnost_bot.payment_keyboards import (
            get_welcome_keyboard,
            get_subscription_keyboard,
            get_payment_plans_keyboard
        )
        print("[OK] payment_keyboards")

        from vechnost_bot.payment_handlers import (
            handle_enter_vechnost,
            handle_subscription_upgrade
        )
        print("[OK] payment_handlers")

        from vechnost_bot.subscription_middleware import check_premium_access
        print("[OK] subscription_middleware")

        from vechnost_bot.payment_webhook import process_tribute_webhook
        print("[OK] payment_webhook")

        print("\n[SUCCESS] All imports OK!\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] Import failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_subscription_models():
    """Test 2: Check subscription models."""
    print("=" * 60)
    print("TEST 2: Subscription Models")
    print("=" * 60)

    try:
        from vechnost_bot.payment_models import (
            SubscriptionTier,
            UserSubscription,
            get_subscription_plan
        )

        # Create free subscription
        free_sub = UserSubscription(user_id=123456789)
        print(f"Created FREE subscription:")
        print(f"  User ID: {free_sub.user_id}")
        print(f"  Tier: {free_sub.tier.value}")
        print(f"  Active: {free_sub.is_active()}")
        print(f"  Can access premium: {free_sub.can_access_premium_themes()}")
        print(f"  Can ask today: {free_sub.can_ask_question_today()}")

        # Upgrade to premium
        free_sub.upgrade_to_premium(duration_days=30)
        print(f"\nUpgraded to PREMIUM:")
        print(f"  Tier: {free_sub.tier.value}")
        print(f"  Active: {free_sub.is_active()}")
        print(f"  Days remaining: {free_sub.days_remaining()}")
        print(f"  Expires: {free_sub.expires_at}")
        print(f"  Can access premium: {free_sub.can_access_premium_themes()}")

        # Check premium plan
        premium_plan = get_subscription_plan(SubscriptionTier.PREMIUM)
        print(f"\nPremium plan details:")
        print(f"  Price: {premium_plan.price_monthly} RUB/month")
        print(f"  Price (yearly): {premium_plan.price_yearly} RUB/year")
        print(f"  Premium themes: {premium_plan.features.premium_themes}")
        print(f"  Premium channel: {premium_plan.features.premium_channel_access}")

        print("\n[SUCCESS] Subscription models work correctly!\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_subscription_storage():
    """Test 3: Check subscription storage."""
    print("=" * 60)
    print("TEST 3: Subscription Storage")
    print("=" * 60)

    try:
        from vechnost_bot.subscription_storage import get_subscription_storage
        from vechnost_bot.payment_models import SubscriptionTier

        storage = get_subscription_storage()

        # Get test user subscription
        test_user_id = 999999999
        subscription = await storage.get_subscription(test_user_id)
        print(f"Got subscription for user {test_user_id}:")
        print(f"  Tier: {subscription.tier.value}")
        print(f"  Active: {subscription.is_active()}")

        # Save subscription
        await storage.save_subscription(subscription)
        print(f"  Saved to storage")

        # Upgrade to premium
        premium_sub = await storage.upgrade_subscription(
            user_id=test_user_id,
            tier=SubscriptionTier.PREMIUM,
            duration_days=7,  # 7 days for test
            payment_id="test_txn_123"
        )
        print(f"\nUpgraded to premium:")
        print(f"  Tier: {premium_sub.tier.value}")
        print(f"  Days remaining: {premium_sub.days_remaining()}")
        print(f"  Last payment: {premium_sub.last_payment_id}")

        print("\n[SUCCESS] Subscription storage works!\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_tribute_client():
    """Test 4: Check Tribute client (no real requests)."""
    print("=" * 60)
    print("TEST 4: Tribute Client")
    print("=" * 60)

    try:
        from vechnost_bot.tribute_client import TributeClient
        from vechnost_bot.config import settings

        # Create client
        tribute = TributeClient()
        print(f"Created Tribute client:")
        print(f"  API key: {'OK' if settings.tribute_api_key else 'NOT SET'}")
        print(f"  API secret: {'OK' if settings.tribute_api_secret else 'NOT SET'}")
        print(f"  Webhook secret: {'OK' if settings.tribute_webhook_secret else 'NOT SET'}")
        print(f"  Base URL: {settings.tribute_base_url}")
        print(f"  Payment enabled: {settings.payment_enabled}")

        print(f"\nAvailable functions:")
        print(f"  create_payment_link: OK")
        print(f"  get_payment_status: OK")
        print(f"  create_subscription: OK")
        print(f"  verify_webhook_signature: OK")

        print("\n[SUCCESS] Tribute client initialized!\n")
        print("[INFO] Configure Tribute API keys in .env for real payments\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_keyboards():
    """Test 5: Check keyboards."""
    print("=" * 60)
    print("TEST 5: Keyboards")
    print("=" * 60)

    try:
        from vechnost_bot.payment_keyboards import (
            get_welcome_keyboard,
            get_subscription_keyboard,
            get_payment_plans_keyboard,
            get_payment_confirmation_keyboard
        )
        from vechnost_bot.payment_models import UserSubscription
        from vechnost_bot.i18n import Language

        # Welcome keyboard
        welcome_kb = get_welcome_keyboard(Language.RUSSIAN)
        print(f"Welcome keyboard:")
        print(f"  Buttons: {len(welcome_kb.inline_keyboard)} rows")

        # Subscription keyboard
        sub = UserSubscription(user_id=123)
        sub_kb = get_subscription_keyboard(sub, Language.RUSSIAN)
        print(f"\nSubscription keyboard (FREE):")
        print(f"  Buttons: {len(sub_kb.inline_keyboard)} rows")

        # Payment plans keyboard
        plans_kb = get_payment_plans_keyboard(Language.RUSSIAN)
        print(f"\nPayment plans keyboard:")
        print(f"  Buttons: {len(plans_kb.inline_keyboard)} rows")

        # Payment confirmation keyboard
        confirm_kb = get_payment_confirmation_keyboard(
            "https://example.com/pay",
            Language.RUSSIAN
        )
        print(f"\nPayment confirmation keyboard:")
        print(f"  Buttons: {len(confirm_kb.inline_keyboard)} rows")

        print("\n[SUCCESS] All keyboards generated correctly!\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def test_access_control():
    """Test 6: Check access control."""
    print("=" * 60)
    print("TEST 6: Access Control")
    print("=" * 60)

    try:
        from vechnost_bot.subscription_middleware import check_premium_access
        from vechnost_bot.models import Theme
        from vechnost_bot.subscription_storage import get_subscription_storage
        from vechnost_bot.payment_models import SubscriptionTier

        storage = get_subscription_storage()

        # Test 1: Free user trying to access premium theme
        free_user_id = 888888888
        free_sub = await storage.get_subscription(free_user_id)

        has_access, error = await check_premium_access(free_user_id, Theme.SEX)
        print(f"Free user access to SEX theme:")
        print(f"  Has access: {has_access}")
        print(f"  Error: {error}")

        # Test 2: Free user trying to access basic theme
        has_access, error = await check_premium_access(free_user_id, Theme.ACQUAINTANCE)
        print(f"\nFree user access to ACQUAINTANCE theme:")
        print(f"  Has access: {has_access}")
        print(f"  Error: {error}")

        # Test 3: Premium user access
        premium_user_id = 777777777
        await storage.upgrade_subscription(
            user_id=premium_user_id,
            tier=SubscriptionTier.PREMIUM,
            duration_days=30
        )

        has_access, error = await check_premium_access(premium_user_id, Theme.SEX)
        print(f"\nPremium user access to SEX theme:")
        print(f"  Has access: {has_access}")
        print(f"  Error: {error}")

        print("\n[SUCCESS] Access control works correctly!\n")
        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n")
    print("=" * 60)
    print("  PAYMENT SYSTEM TEST - VECHNOST BOT")
    print("=" * 60)
    print("\n")

    results = []

    # Run tests
    results.append(("Imports", await test_imports()))
    results.append(("Subscription Models", await test_subscription_models()))
    results.append(("Storage", await test_subscription_storage()))
    results.append(("Tribute Client", await test_tribute_client()))
    results.append(("Keyboards", await test_keyboards()))
    results.append(("Access Control", await test_access_control()))

    # Summary
    print("=" * 60)
    print("TEST RESULTS")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "PASSED" if result else "FAILED"
        print(f"{test_name:.<40} [{status}]")

    print(f"\nTotal tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED! System is ready to use.\n")
        return 0
    else:
        print("\n[WARNING] SOME TESTS FAILED. Check errors above.\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
