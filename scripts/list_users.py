#!/usr/bin/env python3
"""Script to list all users and their subscription status."""

import asyncio
from datetime import datetime

from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.services import user_has_access
from sqlalchemy import select
from vechnost_bot.payments.models import User, Subscription


async def list_users():
    """List all users with their subscription status."""
    print(f"\n{'='*80}")
    print("ALL USERS IN DATABASE")
    print(f"{'='*80}\n")

    async with get_db() as session:
        # Get all users
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        users = result.scalars().all()

        if not users:
            print("❌ No users found in database.\n")
            return

        print(f"Total users: {len(users)}\n")
        print(f"{'─'*80}\n")

        for i, user in enumerate(users, 1):
            # Get user's subscriptions
            sub_result = await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .where(Subscription.status == "active")
                .where(Subscription.end_date > datetime.utcnow())
            )
            active_subs = sub_result.scalars().all()

            # Check access
            has_access = await user_has_access(user.telegram_user_id)
            access_emoji = "✅" if has_access else "❌"

            print(f"{i}. {access_emoji} User ID: {user.telegram_user_id}")
            print(f"   Name: {user.first_name} {user.last_name or ''}".strip())

            if user.username:
                print(f"   Username: @{user.username}")

            print(f"   Registered: {user.created_at.strftime('%Y-%m-%d %H:%M')}")

            if active_subs:
                print(f"   📋 Active subscriptions: {len(active_subs)}")
                for sub in active_subs:
                    days_left = (sub.end_date - datetime.utcnow()).days
                    print(f"      → Expires in {days_left} days ({sub.end_date.strftime('%Y-%m-%d')})")
            else:
                print(f"   📋 No active subscriptions")

            print()

        print(f"{'─'*80}\n")

        # Summary
        users_with_access = sum(1 for _ in filter(
            lambda u: asyncio.run(user_has_access(u.telegram_user_id)),
            users
        ))

        print(f"SUMMARY:")
        print(f"  Total users: {len(users)}")
        print(f"  With access: {users_with_access}")
        print(f"  Without access: {len(users) - users_with_access}")
        print(f"\n{'='*80}\n")


async def main():
    """Main function."""
    await list_users()


if __name__ == "__main__":
    asyncio.run(main())

