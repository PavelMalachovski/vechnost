#!/usr/bin/env python3
"""Script to check user payment status in the database."""

import asyncio
import sys

from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import (
    UserRepository,
)


async def check_user(telegram_user_id: int):
    """Check user information and payment status."""
    print(f"\n{'='*60}")
    print(f"Checking user: {telegram_user_id}")
    print(f"{'='*60}\n")

    async with get_db() as session:
        # Check user
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)

        if user:
            print("✅ USER FOUND:")
            print(f"   ID: {user.id}")
            print(f"   Telegram ID: {user.telegram_user_id}")
            print(f"   Username: @{user.username}" if user.username else "   Username: None")
            print(f"   Name: {user.first_name} {user.last_name or ''}".strip())
            print(f"   Created: {user.created_at}")
        else:
            print("❌ USER NOT FOUND")
            return

        print(f"\n{'─'*60}\n")

        # Check subscriptions
        from sqlalchemy import select

        from vechnost_bot.payments.models import Subscription

        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
        )
        subscriptions = result.scalars().all()

        if subscriptions:
            print(f"📋 SUBSCRIPTIONS ({len(subscriptions)}):")
            for sub in subscriptions:
                status_emoji = "✅" if sub.status == "active" else "⏸️" if sub.status == "paused" else "❌"
                print(f"\n   {status_emoji} Subscription ID: {sub.id}")
                print(f"      Tribute ID: {sub.tribute_subscription_id}")
                print(f"      Status: {sub.status}")
                print(f"      Starts: {sub.start_date}")
                print(f"      Ends: {sub.end_date}" if sub.end_date else "      Ends: No end date")
                print(f"      Created: {sub.created_at}")
        else:
            print("📋 SUBSCRIPTIONS: None")

        print(f"\n{'─'*60}\n")

        # Check payments
        from vechnost_bot.payments.models import Payment

        result = await session.execute(
            select(Payment)
            .where(Payment.user_id == user.id)
            .order_by(Payment.created_at.desc())
        )
        payments = result.scalars().all()

        if payments:
            print(f"💳 PAYMENTS ({len(payments)}):")
            for payment in payments:
                status_emoji = "✅" if payment.status == "succeeded" else "⏳" if payment.status == "pending" else "❌"
                print(f"\n   {status_emoji} Payment ID: {payment.id}")
                print(f"      Tribute ID: {payment.tribute_payment_id}")
                print(f"      Amount: {payment.amount} {payment.currency}")
                print(f"      Status: {payment.status}")
                print(f"      Created: {payment.created_at}")
        else:
            print("💳 PAYMENTS: None")

        print(f"\n{'─'*60}\n")

        # Check webhook events
        from vechnost_bot.payments.models import WebhookEvent

        result = await session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.telegram_user_id == telegram_user_id)
            .order_by(WebhookEvent.created_at.desc())
            .limit(10)
        )
        events = result.scalars().all()

        if events:
            print(f"🔔 RECENT WEBHOOK EVENTS ({len(events)}):")
            for event in events:
                status_emoji = "✅" if event.processed else "⏳"
                print(f"\n   {status_emoji} Event ID: {event.id}")
                print(f"      Type: {event.event_type}")
                print(f"      Tribute ID: {event.tribute_event_id}")
                print(f"      Processed: {event.processed}")
                print(f"      Created: {event.created_at}")
        else:
            print("🔔 WEBHOOK EVENTS: None")

        print(f"\n{'='*60}")

        # Final access check
        from vechnost_bot.payments.services import user_has_access
        has_access = await user_has_access(telegram_user_id)

        if has_access:
            print("🎉 RESULT: USER HAS ACTIVE ACCESS ✅")
        else:
            print("⚠️  RESULT: USER DOES NOT HAVE ACCESS ❌")

        print(f"{'='*60}\n")


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python check_user_payment.py <telegram_user_id>")
        print("Example: python check_user_payment.py 1115719673")
        sys.exit(1)

    try:
        telegram_user_id = int(sys.argv[1])
    except ValueError:
        print("Error: telegram_user_id must be a number")
        sys.exit(1)

    await check_user(telegram_user_id)


if __name__ == "__main__":
    asyncio.run(main())

