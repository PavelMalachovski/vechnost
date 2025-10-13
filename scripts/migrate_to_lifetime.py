#!/usr/bin/env python3
"""Migrate database to support lifetime subscriptions."""

import asyncio
import os
import asyncpg


async def migrate():
    """Apply migration to make expires_at nullable."""

    database_url = os.getenv('DATABASE_URL', '').replace('postgresql+asyncpg://', 'postgresql://')

    if not database_url:
        print("[X] DATABASE_URL not found!")
        return False

    try:
        conn = await asyncpg.connect(database_url)

        print("[*] Applying migration...")

        # 1. Make expires_at nullable
        await conn.execute('ALTER TABLE subscriptions ALTER COLUMN expires_at DROP NOT NULL')
        print("[OK] Made expires_at nullable")

        # 2. Update user 1115719673 to lifetime
        await conn.execute("""
            UPDATE subscriptions
            SET expires_at = NULL, period = 'lifetime'
            WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = 1115719673)
            AND status = 'active'
        """)
        print("[OK] Updated user 1115719673 to lifetime subscription")

        # 3. Verify
        result = await conn.fetchrow("""
            SELECT
                u.telegram_user_id,
                u.first_name,
                s.period,
                s.expires_at,
                s.status
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.telegram_user_id = 1115719673
            AND s.status = 'active'
        """)

        if result:
            print(f"\n[SUCCESS] Migration complete!")
            print(f"  User: {result['first_name']} ({result['telegram_user_id']})")
            print(f"  Period: {result['period']}")
            print(f"  Expires: {'LIFETIME (Never)' if result['expires_at'] is None else result['expires_at']}")
            print(f"  Status: {result['status']}")
        else:
            print("\n[!] Warning: No active subscription found for user 1115719673")

        await conn.close()
        return True

    except Exception as e:
        print(f"[X] Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(migrate())
    exit(0 if success else 1)

