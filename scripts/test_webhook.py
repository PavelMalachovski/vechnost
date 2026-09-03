"""Send a Tribute-shaped webhook to a local server, signed the way Tribute signs.

    python scripts/test_webhook.py                # new_digital_product for a fake buyer
    python scripts/test_webhook.py cancelled_subscription --user 123456789
    python scripts/test_webhook.py --bad-signature  # must come back 401

The body is signed with HMAC-SHA256 keyed by TRIBUTE_API_KEY (or
WEBHOOK_SECRET when that is what the server trusts) and sent in the
`trbt-signature` header, byte for byte: the signature covers exactly the
bytes on the wire, so the body is encoded once and sent as-is.
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhooks/tribute")


def signing_key() -> str:
    key = os.getenv("TRIBUTE_API_KEY") or os.getenv("WEBHOOK_SECRET") or ""
    if not key:
        sys.exit("Set TRIBUTE_API_KEY (or WEBHOOK_SECRET) so the delivery can be signed")
    return key


def build(name: str, telegram_user_id: int, product_id: int) -> bytes:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "name": name,
        "created_at": now,
        "sent_at": now,
        "payload": {
            "product_id": product_id,
            "product_name": "VECHNOST",
            "amount": 990,
            "currency": "eur",
            "user_id": 100,
            "telegram_user_id": telegram_user_id,
        },
    }
    return json.dumps(body, ensure_ascii=False).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("name", nargs="?", default="new_digital_product",
                        help="event name (new_digital_product, cancelled_subscription, ...)")
    parser.add_argument("--user", type=int, default=123456789, help="telegram_user_id")
    parser.add_argument("--product", type=int, default=1, help="product_id")
    parser.add_argument("--bad-signature", action="store_true",
                        help="sign with a wrong key; the server must answer 401")
    args = parser.parse_args()

    body = build(args.name, args.user, args.product)
    key = "wrong-key" if args.bad_signature else signing_key()
    signature = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()

    print(f"POST {WEBHOOK_URL}")
    print(body.decode())
    response = httpx.post(
        WEBHOOK_URL,
        content=body,
        headers={"Content-Type": "application/json", "trbt-signature": signature},
        timeout=30.0,
    )
    print(f"\n{response.status_code} {response.text}")


if __name__ == "__main__":
    main()
