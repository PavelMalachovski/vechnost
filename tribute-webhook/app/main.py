"""
FastAPI application for Tribute payment webhook handling.
"""
import hashlib
import hmac
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, init_db
from app import crud, schemas
from app.models import WebhookEvent

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    await init_db()
    yield


app = FastAPI(
    title="Tribute Webhook Handler",
    description="Secure webhook handler for Tribute payment events",
    version="1.0.0",
    lifespan=lifespan
)


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature from Tribute webhook"""
    if not settings.TRIBUTE_API_KEY:
        return False

    expected_signature = hmac.new(
        settings.TRIBUTE_API_KEY.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def compute_body_sha256(raw_body: bytes) -> str:
    """Compute SHA256 hash of request body for idempotency"""
    return hashlib.sha256(raw_body).hexdigest()


@app.post("/webhook/tribute", response_model=schemas.WebhookResponse)
async def tribute_webhook(request: Request):
    """
    Handle Tribute payment webhook events.

    Events handled:
    - new_digital_product: One-time payment for digital product
    - new_subscription: New recurring subscription created
    - cancelled_subscription: Subscription cancelled

    Returns 401 if signature invalid, 200 with idempotency flag if duplicate.
    """
    # Read raw body bytes
    raw_body = await request.body()

    # Verify signature
    signature = request.headers.get("trbt-signature", "")
    if not verify_signature(raw_body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )

    # Parse JSON body
    try:
        body = json.loads(raw_body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body"
        )

    # Compute body hash for idempotency
    body_sha256 = compute_body_sha256(raw_body)

    # Get database session
    async for db in get_db():
        break

    # Check for duplicate webhook
    existing = await crud.get_payment_by_body_hash(db, body_sha256)
    if existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True, "dup": True}
        )

    # Extract event name
    event_name = body.get("event_name") or body.get("event")
    if not event_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event_name"
        )

    # Create webhook event record
    webhook_event = await crud.create_webhook_event(
        db,
        name=event_name,
        body_sha256=body_sha256,
        sent_at=body.get("sent_at"),
        raw_body=body
    )

    # Handle different event types
    try:
        if event_name == "new_digital_product":
            await handle_new_digital_product(db, body, body_sha256, signature)
        elif event_name == "new_subscription":
            await handle_new_subscription(db, body, body_sha256, signature)
        elif event_name == "cancelled_subscription":
            await handle_cancelled_subscription(db, body, body_sha256, signature)
        else:
            # Unknown event, just log it
            pass

        # Mark webhook as processed
        await crud.mark_webhook_processed(db, webhook_event.id, None)

    except Exception as e:
        # Mark webhook as failed with error
        await crud.mark_webhook_processed(db, webhook_event.id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing webhook: {str(e)}"
        )

    return {"ok": True}


async def handle_new_digital_product(
    db: AsyncSession,
    body: dict,
    body_sha256: str,
    signature: str
):
    """Handle new_digital_product event (one-time payment)"""
    telegram_user_id = body.get("telegram_user_id")
    product_id = body.get("product_id")
    amount = body.get("amount")
    currency = body.get("currency", "RUB")

    # Upsert user
    user = await crud.upsert_user(
        db,
        telegram_user_id=telegram_user_id,
        username=body.get("username"),
        first_name=body.get("first_name"),
        last_name=body.get("last_name")
    )

    # Create payment record
    await crud.create_payment(
        db,
        event_name="new_digital_product",
        user_id=user.id,
        telegram_user_id=telegram_user_id,
        product_id=product_id,
        amount=amount,
        currency=currency,
        raw_body=body,
        signature=signature,
        body_sha256=body_sha256
    )


async def handle_new_subscription(
    db: AsyncSession,
    body: dict,
    body_sha256: str,
    signature: str
):
    """Handle new_subscription event"""
    telegram_user_id = body.get("telegram_user_id")
    subscription_id = body.get("subscription_id")
    period = body.get("period")
    amount = body.get("amount")
    currency = body.get("currency", "RUB")
    expires_at = body.get("expires_at")

    # Upsert user
    user = await crud.upsert_user(
        db,
        telegram_user_id=telegram_user_id,
        username=body.get("username"),
        first_name=body.get("first_name"),
        last_name=body.get("last_name")
    )

    # Create payment record
    await crud.create_payment(
        db,
        event_name="new_subscription",
        user_id=user.id,
        telegram_user_id=telegram_user_id,
        amount=amount,
        currency=currency,
        expires_at=expires_at,
        raw_body=body,
        signature=signature,
        body_sha256=body_sha256
    )

    # Upsert subscription
    await crud.upsert_subscription(
        db,
        user_id=user.id,
        subscription_id=subscription_id,
        period=period,
        status="active",
        expires_at=expires_at
    )


async def handle_cancelled_subscription(
    db: AsyncSession,
    body: dict,
    body_sha256: str,
    signature: str
):
    """Handle cancelled_subscription event"""
    telegram_user_id = body.get("telegram_user_id")
    subscription_id = body.get("subscription_id")

    # Find user
    user = await crud.get_user_by_telegram_id(db, telegram_user_id)
    if not user:
        return  # No user, nothing to cancel

    # Create payment record (for audit trail)
    await crud.create_payment(
        db,
        event_name="cancelled_subscription",
        user_id=user.id,
        telegram_user_id=telegram_user_id,
        raw_body=body,
        signature=signature,
        body_sha256=body_sha256
    )

    # Update subscription status
    await crud.update_subscription_status(
        db,
        user_id=user.id,
        subscription_id=subscription_id,
        status="cancelled"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "tribute-webhook"}

