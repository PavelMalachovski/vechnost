"""Simple user payment checker without emoji (Windows-friendly)."""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Import payment modules
from vechnost_bot.payments.database import get_db, init_db
from vechnost_bot.payments.repositories import UserRepository
from sqlalchemy import select
from vechnost_bot.payments.models import Subscription, Payment


async def check_user(telegram_user_id: int):
    """Check user payment and subscription status."""
    init_db()

    print("="*60)
    print(f"Checking user: {telegram_user_id}")
    print("="*60 + "\n")

    async with get_db() as session:
        # Check user
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)

        if user:
            print("[OK] USER FOUND:")
            print(f"   ID: {user.id}")
            print(f"   Telegram ID: {user.telegram_user_id}")
            print(f"   Username: @{user.username}" if user.username else "   Username: None")
            print(f"   Name: {user.first_name} {user.last_name or ''}".strip())
            print(f"   Created: {user.created_at}")
        else:
            print("[X] USER NOT FOUND")
            return

        print(f"\n{'-'*60}\n")

        # Check subscriptions
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.last_event_at.desc())
        )
        subscriptions = list(result.scalars().all())

        if subscriptions:
            print(f"[*] SUBSCRIPTIONS ({len(subscriptions)}):")
            for sub in subscriptions:
                status_marker = "[OK]" if sub.status == "active" else "[X]"
                print(f"\n   {status_marker} Subscription #{sub.id}")
                print(f"      Tribute Subscription ID: {sub.subscription_id}")
                print(f"      Status: {sub.status}")
                print(f"      Period: {sub.period}")
                if sub.expires_at:
                    print(f"      Expires: {sub.expires_at}")
                else:
                    print(f"      Expires: LIFETIME (Never)")
                print(f"      Last Event: {sub.last_event_at}")
        else:
            print("[X] NO SUBSCRIPTIONS FOUND")

        print(f"\n{'-'*60}\n")

        # Check payments
        result = await session.execute(
            select(Payment)
            .where(Payment.user_id == user.id)
            .order_by(Payment.created_at.desc())
        )
        payments = list(result.scalars().all())

        if payments:
            print(f"[*] PAYMENTS ({len(payments)}):")
            for payment in payments:
                print(f"\n   Payment ID: {payment.id}")
                print(f"      Event: {payment.event_name}")
                print(f"      Amount: {payment.amount} {payment.currency}")
                print(f"      Provider: {payment.provider}")
                print(f"      Created: {payment.created_at}")
                if payment.expires_at:
                    print(f"      Expires: {payment.expires_at}")
        else:
            print("[X] NO PAYMENTS FOUND")

        print(f"\n{'='*60}\n")

        # Check active access
        from datetime import datetime
        from vechnost_bot.payments.repositories import SubscriptionRepository

        active_subs = await SubscriptionRepository.get_active_subscriptions_for_user(
            session, user.id
        )

        if active_subs:
            print(f"[SUCCESS] USER HAS ACTIVE ACCESS")
            print(f"          Active subscriptions: {len(active_subs)}")
            for sub in active_subs:
                if sub.is_lifetime:
                    print(f"          - Subscription #{sub.id}: LIFETIME (Never expires)")
                else:
                    print(f"          - Subscription #{sub.id}: Expires {sub.expires_at}")
        else:
            print(f"[WARNING] NO ACTIVE ACCESS")

        print(f"\n{'='*60}")


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python check_user_simple.py <telegram_user_id>")
        sys.exit(1)

    try:
        telegram_user_id = int(sys.argv[1])
    except ValueError:
        print("[X] Error: telegram_user_id must be a number")
        sys.exit(1)

    await check_user(telegram_user_id)


if __name__ == "__main__":
    asyncio.run(main())

