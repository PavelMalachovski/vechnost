"""Check local SQLite database."""
import asyncio
import aiosqlite


async def check_all():
    """Check all data in local SQLite database."""
    print("\n[*] Connecting to vechnost.db...")

    try:
        async with aiosqlite.connect('vechnost.db') as db:
            # Get all users
            async with db.execute('SELECT * FROM users') as cursor:
                users = await cursor.fetchall()

                print(f"\n{'='*60}")
                print(f"USERS ({len(users)})")
                print('='*60)

                if not users:
                    print("  (empty)")
                else:
                    for user in users:
                        print(f"\n[{user[0]}] User {user[1]}")
                        print(f"    Username: @{user[2]}" if user[2] else "    Username: None")
                        print(f"    Name: {user[3]} {user[4] or ''}".strip())

            # Get all subscriptions
            async with db.execute('''
                SELECT s.*, u.telegram_user_id
                FROM subscriptions s
                JOIN users u ON u.id = s.user_id
            ''') as cursor:
                subscriptions = await cursor.fetchall()

                print(f"\n{'='*60}")
                print(f"SUBSCRIPTIONS ({len(subscriptions)})")
                print('='*60)

                if not subscriptions:
                    print("  (empty)")
                else:
                    for sub in subscriptions:
                        print(f"\n[{sub[0]}] Subscription {sub[2]}")
                        print(f"    User: {sub[7]}")
                        print(f"    Status: {sub[4]}")
                        print(f"    Period: {sub[3]}")
                        if sub[5]:
                            print(f"    Expires: {sub[5]}")
                        else:
                            print(f"    Expires: LIFETIME (Never)")

            # Get all payments
            async with db.execute('''
                SELECT p.*, u.telegram_user_id
                FROM payments p
                JOIN users u ON u.id = p.user_id
            ''') as cursor:
                payments = await cursor.fetchall()

                print(f"\n{'='*60}")
                print(f"PAYMENTS ({len(payments)})")
                print('='*60)

                if not payments:
                    print("  (empty)")
                else:
                    for payment in payments:
                        print(f"\n[{payment[0]}] Payment")
                        print(f"    User: {payment[12]}")
                        print(f"    Event: {payment[2]}")
                        print(f"    Amount: {payment[5]} {payment[6]}")

            # Get webhook events
            async with db.execute('''
                SELECT * FROM webhook_events
                ORDER BY created_at DESC
                LIMIT 10
            ''') as cursor:
                webhooks = await cursor.fetchall()

                print(f"\n{'='*60}")
                print(f"WEBHOOK EVENTS (last 10)")
                print('='*60)

                if not webhooks:
                    print("  (empty)")
                else:
                    for wh in webhooks:
                        print(f"\n[{wh[0]}] {wh[1]}")
                        print(f"    Status: {wh[5]}")
                        if wh[7]:
                            print(f"    Error: {wh[7]}")

            print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"\n[X] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_all())

