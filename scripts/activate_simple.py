#!/usr/bin/env python3
"""Simple activation script that uses environment variables from Railway."""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# Use asyncpg directly with environment variable
import asyncpg


async def activate_user(telegram_user_id: int, days: int = None):
    """Activate user directly with asyncpg."""

    # Get DATABASE_URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("[X] DATABASE_URL not found!")
        return False

    # Convert postgresql+asyncpg:// to postgresql://
    database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')

    print(f"\n[*] Activating user {telegram_user_id} for {days} days...")

    try:
        # Connect to database
        conn = await asyncpg.connect(database_url)

        # 1. Check if user exists
        user = await conn.fetchrow(
            'SELECT * FROM users WHERE telegram_user_id = $1',
            telegram_user_id
        )

        if not user:
            print(f"[X] User {telegram_user_id} not found in database!")
            print("    User must use the bot first (/start)")
            await conn.close()
            return False

        print(f"[OK] Found user: {user['first_name']} {user['last_name'] or ''}")

        # 2. Check existing subscriptions
        existing = await conn.fetch(
            """SELECT * FROM subscriptions
               WHERE user_id = $1 AND status = 'active' AND expires_at > NOW()""",
            user['id']
        )

        if existing:
            print(f"\n[!] User already has {len(existing)} active subscription(s):")
            for sub in existing:
                print(f"    - Expires: {sub['expires_at']}")

            # Cancel existing subscriptions
            await conn.execute(
                """UPDATE subscriptions
                   SET status = 'cancelled', expires_at = NOW()
                   WHERE user_id = $1 AND status = 'active'""",
                user['id']
            )
            print("    Cancelled existing subscriptions.")

        # 3. Create new subscription
        start_date = datetime.utcnow()
        subscription_id = int(start_date.timestamp())  # Use timestamp as subscription_id

        if days is None:
            # Lifetime subscription
            expires_at = None
            period = 'lifetime'
            print(f"\n[*] Creating LIFETIME subscription...")
        else:
            # Time-limited subscription
            expires_at = start_date + timedelta(days=days)
            period = f'{days}d'
            print(f"\n[*] Creating subscription for {days} days...")

        await conn.execute(
            """INSERT INTO subscriptions
               (user_id, subscription_id, period, status, expires_at, last_event_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user['id'], subscription_id, period, 'active', expires_at, start_date
        )

        print(f"\n[OK] SUBSCRIPTION ACTIVATED!")
        print(f"     Created: {start_date}")
        if expires_at:
            print(f"     Expires: {expires_at}")
            print(f"     Duration: {days} days")
        else:
            print(f"     Expires: NEVER (Lifetime)")
        print(f"\n[SUCCESS] User {telegram_user_id} now has access to the bot!\n")

        await conn.close()
        return True

    except Exception as e:
        print(f"[X] Error: {e}")
        return False


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python activate_simple.py <telegram_user_id> [days|lifetime]")
        print("\nExamples:")
        print("  python activate_simple.py 1115719673 30        # 30 days")
        print("  python activate_simple.py 1115719673 lifetime  # Forever")
        print("  python activate_simple.py 1115719673           # Forever (default)")
        sys.exit(1)

    try:
        telegram_user_id = int(sys.argv[1])
    except ValueError:
        print("[X] Error: telegram_user_id must be a number")
        sys.exit(1)

    days = None  # Default: lifetime
    if len(sys.argv) >= 3:
        if sys.argv[2].lower() in ['lifetime', 'forever', 'permanent']:
            days = None
        else:
            try:
                days = int(sys.argv[2])
            except ValueError:
                print("[X] Error: days must be a number or 'lifetime'")
                sys.exit(1)

    success = await activate_user(telegram_user_id, days)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

