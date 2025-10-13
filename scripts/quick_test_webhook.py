"""Quick webhook test - send a test subscription.created event."""
import asyncio
import json
import httpx
from datetime import datetime, timedelta

WEBHOOK_URL = "http://127.0.0.1:8000/webhooks/tribute"

async def test():
    """Send test webhook."""
    # Test: Lifetime subscription for user 1115719673
    payload = {
        "event": "subscription.created",
        "data": {
            "id": 99999,
            "customer": {
                "id": 67890,
                "email": "test@example.com",
                "telegram_user_id": "1115719673"
            },
            "product": {
                "id": 222,
                "name": "Vechnost Lifetime",
                "price": 5990
            },
            "period": "lifetime",
            "status": "active",
            "expires_at": None  # Lifetime!
        }
    }

    print("=" * 60)
    print("[*] Sending LIFETIME subscription webhook for user 1115719673")
    print("=" * 60)
    print("\nPayload:")
    print(json.dumps(payload, indent=2))
    print("\n" + "=" * 60)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            print(f"\n[OK] Response: {response.status_code}")
            print(f"Body:\n{response.text}")

            if response.status_code == 200:
                print("\n[SUCCESS] Webhook processed!")
                print("\nNext steps:")
                print("1. Check user access: python check_user_payment.py 1115719673")
                print("2. Try logging into bot as user 1115719673")
            else:
                print(f"\n[ERROR] Status: {response.status_code}")

    except Exception as e:
        print(f"\n[ERROR] {e}")

if __name__ == "__main__":
    asyncio.run(test())

