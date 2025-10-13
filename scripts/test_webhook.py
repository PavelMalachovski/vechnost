"""
Test script for Tribute webhook endpoint.

This script simulates Tribute webhook events for testing.
"""
import asyncio
import json
import hmac
import hashlib
from datetime import datetime, timedelta
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhooks/tribute")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def generate_signature(payload: dict, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook."""
    payload_str = json.dumps(payload, separators=(',', ':'))
    signature = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature


async def send_webhook(event_type: str, payload: dict):
    """Send webhook to the server."""
    print(f"\n{'='*60}")
    print(f"📤 Sending {event_type} webhook...")
    print(f"{'='*60}")

    # Generate signature if secret is provided
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        signature = generate_signature(payload, WEBHOOK_SECRET)
        headers["X-Tribute-Signature"] = signature
        print(f"🔐 Signature: {signature[:20]}...")

    print(f"\n📋 Payload:")
    print(json.dumps(payload, indent=2))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers=headers
            )

            print(f"\n✅ Response: {response.status_code}")
            print(f"📄 Body: {response.text}")

            return response

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None


async def test_subscription_created():
    """Test subscription.created event."""
    payload = {
        "event": "subscription.created",
        "data": {
            "id": 12345,
            "customer": {
                "id": 67890,
                "email": "test@example.com",
                "telegram_user_id": "1115719673"  # Your test user
            },
            "product": {
                "id": 111,
                "name": "Vechnost Premium",
                "price": 990
            },
            "period": "1m",  # 1 month
            "status": "active",
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
        }
    }

    await send_webhook("subscription.created", payload)


async def test_subscription_renewed():
    """Test subscription.renewed event."""
    payload = {
        "event": "subscription.renewed",
        "data": {
            "id": 12345,
            "customer": {
                "id": 67890,
                "telegram_user_id": "1115719673"
            },
            "status": "active",
            "expires_at": (datetime.utcnow() + timedelta(days=60)).isoformat() + "Z"
        }
    }

    await send_webhook("subscription.renewed", payload)


async def test_subscription_cancelled():
    """Test subscription.cancelled event."""
    payload = {
        "event": "subscription.cancelled",
        "data": {
            "id": 12345,
            "customer": {
                "id": 67890,
                "telegram_user_id": "1115719673"
            },
            "status": "cancelled",
            "cancelled_at": datetime.utcnow().isoformat() + "Z"
        }
    }

    await send_webhook("subscription.cancelled", payload)


async def test_payment_completed():
    """Test payment.completed event."""
    payload = {
        "event": "payment.completed",
        "data": {
            "id": 54321,
            "customer": {
                "id": 67890,
                "email": "test@example.com",
                "telegram_user_id": "1115719673"
            },
            "product": {
                "id": 111,
                "name": "Vechnost Premium"
            },
            "amount": 990,
            "currency": "RUB",
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z"
        }
    }

    await send_webhook("payment.completed", payload)


async def test_lifetime_subscription():
    """Test lifetime subscription creation."""
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
            "expires_at": None  # Lifetime = no expiration
        }
    }

    await send_webhook("subscription.created (LIFETIME)", payload)


async def test_health_check():
    """Test health check endpoint."""
    print(f"\n{'='*60}")
    print(f"🏥 Testing health check...")
    print(f"{'='*60}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(WEBHOOK_URL.replace("/webhooks/tribute", "/health"))
            print(f"\n✅ Health check: {response.status_code}")
            print(f"📄 Response: {response.json()}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


async def main():
    """Main test function."""
    print("\n🚀 Tribute Webhook Tester")
    print(f"🎯 Target: {WEBHOOK_URL}")
    print(f"🔐 Secret: {'✅ Configured' if WEBHOOK_SECRET else '❌ Not configured'}")

    # Test health check first
    await test_health_check()

    # Menu
    while True:
        print("\n" + "="*60)
        print("📋 Select test:")
        print("="*60)
        print("1. Test subscription.created (30 days)")
        print("2. Test subscription.renewed")
        print("3. Test subscription.cancelled")
        print("4. Test payment.completed")
        print("5. Test LIFETIME subscription")
        print("6. Run all tests")
        print("0. Exit")
        print("="*60)

        choice = input("\n👉 Enter choice: ").strip()

        if choice == "0":
            print("\n👋 Bye!")
            break
        elif choice == "1":
            await test_subscription_created()
        elif choice == "2":
            await test_subscription_renewed()
        elif choice == "3":
            await test_subscription_cancelled()
        elif choice == "4":
            await test_payment_completed()
        elif choice == "5":
            await test_lifetime_subscription()
        elif choice == "6":
            print("\n🔄 Running all tests...")
            await test_subscription_created()
            await asyncio.sleep(1)
            await test_subscription_renewed()
            await asyncio.sleep(1)
            await test_payment_completed()
            await asyncio.sleep(1)
            await test_lifetime_subscription()
            await asyncio.sleep(1)
            await test_subscription_cancelled()
        else:
            print("❌ Invalid choice")

        input("\n⏸️  Press Enter to continue...")


if __name__ == "__main__":
    asyncio.run(main())

