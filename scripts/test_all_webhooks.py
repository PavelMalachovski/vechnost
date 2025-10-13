"""Test all webhook types."""
import asyncio
import json
import httpx
from datetime import datetime, timedelta

WEBHOOK_URL = "http://127.0.0.1:8000/webhooks/tribute"


async def send_webhook(name, payload):
    """Send webhook."""
    print("\n" + "="*60)
    print(f"[*] Testing: {name}")
    print("="*60)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            print(f"[OK] Status: {response.status_code}")
            print(f"Response: {response.text}")

            return response.status_code == 200

    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_30day_subscription():
    """Test 30-day subscription."""
    payload = {
        "event": "subscription.created",
        "data": {
            "id": 10001,
            "customer": {
                "telegram_user_id": "540529430",
                "email": "test2@example.com"
            },
            "product": {
                "id": 111,
                "name": "Vechnost 30 Days",
                "price": 990
            },
            "period": "30d",
            "status": "active",
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
        }
    }

    return await send_webhook("30-Day Subscription", payload)


async def test_renewal():
    """Test subscription renewal."""
    payload = {
        "event": "subscription.renewed",
        "data": {
            "id": 10001,
            "customer": {
                "telegram_user_id": "540529430"
            },
            "status": "active",
            "expires_at": (datetime.utcnow() + timedelta(days=60)).isoformat() + "Z"
        }
    }

    return await send_webhook("Subscription Renewal", payload)


async def test_payment():
    """Test payment completed."""
    payload = {
        "event": "payment.completed",
        "data": {
            "id": 50001,
            "customer": {
                "telegram_user_id": "540529430"
            },
            "product": {
                "id": 111,
                "name": "Vechnost 30 Days"
            },
            "amount": 990,
            "currency": "RUB",
            "status": "completed"
        }
    }

    return await send_webhook("Payment Completed", payload)


async def test_cancellation():
    """Test subscription cancellation."""
    payload = {
        "event": "subscription.cancelled",
        "data": {
            "id": 10001,
            "customer": {
                "telegram_user_id": "540529430"
            },
            "status": "cancelled"
        }
    }

    return await send_webhook("Subscription Cancelled", payload)


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TRIBUTE WEBHOOK TEST SUITE")
    print("="*60)

    results = {}

    # Test 1: 30-day subscription for user 540529430
    results['30-day'] = await test_30day_subscription()
    await asyncio.sleep(0.5)

    # Test 2: Payment
    results['payment'] = await test_payment()
    await asyncio.sleep(0.5)

    # Test 3: Renewal
    results['renewal'] = await test_renewal()
    await asyncio.sleep(0.5)

    # Test 4: Cancellation
    results['cancel'] = await test_cancellation()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {test_name}")

    print("\n" + "="*60)
    print("Next steps:")
    print("1. Check user 540529430: python check_user_simple.py 540529430")
    print("2. Check user 1115719673: python check_user_simple.py 1115719673")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

