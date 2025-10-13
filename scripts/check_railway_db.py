"""Check Railway PostgreSQL database directly."""
import asyncio
import os
import sys
import asyncpg


async def check_all_users():
    """Check all users in Railway database."""
    database_url = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./vechnost.db')

    # Convert to asyncpg format
    database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')

    print(f"\n[*] Connecting to: {database_url[:50]}...")

    try:
        conn = await asyncpg.connect(database_url)

        # Get all users
        users = await conn.fetch('SELECT * FROM users ORDER BY id')

        print(f"\n{'='*60}")
        print(f"USERS ({len(users)})")
        print('='*60)

        for user in users:
            print(f"\n[{user['id']}] User {user['telegram_user_id']}")
            print(f"    Username: @{user['username']}" if user['username'] else "    Username: None")
            print(f"    Name: {user['first_name']} {user['last_name'] or ''}".strip())
            print(f"    Created: {user['created_at']}")

        # Get all subscriptions
        print(f"\n{'='*60}")
        print("SUBSCRIPTIONS")
        print('='*60)

        subscriptions = await conn.fetch(
            """SELECT s.*, u.telegram_user_id
               FROM subscriptions s
               JOIN users u ON u.id = s.user_id
               ORDER BY s.id"""
        )

        for sub in subscriptions:
            print(f"\n[{sub['id']}] Subscription {sub['subscription_id']}")
            print(f"    User: {sub['telegram_user_id']}")
            print(f"    Status: {sub['status']}")
            print(f"    Period: {sub['period']}")
            if sub['expires_at']:
                print(f"    Expires: {sub['expires_at']}")
            else:
                print(f"    Expires: LIFETIME (Never)")
            print(f"    Last Event: {sub['last_event_at']}")

        # Get all payments
        print(f"\n{'='*60}")
        print("PAYMENTS")
        print('='*60)

        payments = await conn.fetch(
            """SELECT p.*, u.telegram_user_id
               FROM payments p
               JOIN users u ON u.id = p.user_id
               ORDER BY p.id"""
        )

        for payment in payments:
            print(f"\n[{payment['id']}] Payment")
            print(f"    User: {payment['telegram_user_id']}")
            print(f"    Event: {payment['event_name']}")
            print(f"    Amount: {payment['amount']} {payment['currency']}")
            print(f"    Created: {payment['created_at']}")

        # Get webhook events
        print(f"\n{'='*60}")
        print("WEBHOOK EVENTS (last 10)")
        print('='*60)

        webhooks = await conn.fetch(
            """SELECT * FROM webhook_events
               ORDER BY created_at DESC
               LIMIT 10"""
        )

        for wh in webhooks:
            print(f"\n[{wh['id']}] {wh['name']}")
            print(f"    Created: {wh['created_at']}")
            print(f"    Sent At: {wh['sent_at']}")
            print(f"    Status: {wh['status_code']}")
            if wh['processed_at']:
                print(f"    Processed: {wh['processed_at']}")
            if wh['error']:
                print(f"    Error: {wh['error']}")

        print(f"\n{'='*60}\n")

        await conn.close()

    except Exception as e:
        print(f"\n[X] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_all_users())

