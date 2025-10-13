#!/usr/bin/env python3
"""Script to manually activate a user (for testing or manual subscription)."""

import asyncio
import sys
from datetime import datetime, timedelta

from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository, SubscriptionRepository


async def activate_user(telegram_user_id: int, duration_days: int = 30):
    """Manually activate a user with a subscription."""
    print(f"\nActivating user {telegram_user_id} for {duration_days} days...")

    async with get_db() as session:
        # Check if user exists
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)

        if not user:
            print(f"❌ User {telegram_user_id} not found in database.")
            print("   User must interact with bot first (e.g., /start)")
            return False

        print(f"✅ Found user: {user.first_name} {user.last_name or ''}".strip())

        # Check existing active subscriptions
        from sqlalchemy import select
        from vechnost_bot.payments.models import Subscription

        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status == "active")
            .where(Subscription.end_date > datetime.utcnow())
        )
        active_subs = result.scalars().all()

        if active_subs:
            print(f"\n⚠️  User already has {len(active_subs)} active subscription(s):")
            for sub in active_subs:
                print(f"   - Ends: {sub.end_date}")

            response = input("\nDeactivate existing subscriptions? (y/n): ")
            if response.lower() == 'y':
                for sub in active_subs:
                    sub.status = "cancelled"
                    sub.end_date = datetime.utcnow()
                await session.commit()
                print("   Deactivated existing subscriptions.")

        # Create new subscription
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=duration_days)

        subscription = await SubscriptionRepository.create(
            session,
            user_id=user.id,
            tribute_subscription_id=f"manual_{telegram_user_id}_{int(start_date.timestamp())}",
            status="active",
            start_date=start_date,
            end_date=end_date,
        )

        print(f"\n✅ SUBSCRIPTION ACTIVATED!")
        print(f"   Subscription ID: {subscription.id}")
        print(f"   Start: {start_date}")
        print(f"   End: {end_date}")
        print(f"   Duration: {duration_days} days")
        print(f"\n🎉 User {telegram_user_id} now has access to the bot!\n")

        return True


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python activate_user.py <telegram_user_id> [duration_days]")
        print("\nExamples:")
        print("  python activate_user.py 1115719673         # 30 days (default)")
        print("  python activate_user.py 1115719673 365     # 365 days (1 year)")
        print("  python activate_user.py 1115719673 7       # 7 days (trial)")
        sys.exit(1)

    try:
        telegram_user_id = int(sys.argv[1])
    except ValueError:
        print("Error: telegram_user_id must be a number")
        sys.exit(1)

    duration_days = 30  # Default
    if len(sys.argv) >= 3:
        try:
            duration_days = int(sys.argv[2])
        except ValueError:
            print("Error: duration_days must be a number")
            sys.exit(1)

    success = await activate_user(telegram_user_id, duration_days)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

