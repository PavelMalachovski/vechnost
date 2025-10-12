"""
CRUD operations for database models.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app import models


async def get_user_by_telegram_id(
    db: AsyncSession,
    telegram_user_id: int
) -> Optional[models.User]:
    """Get user by Telegram user ID"""
    result = await db.execute(
        select(models.User).where(models.User.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def upsert_user(
    db: AsyncSession,
    telegram_user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> models.User:
    """Insert or update user"""
    stmt = sqlite_upsert(models.User).values(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )

    # On conflict, update username, first_name, last_name
    stmt = stmt.on_conflict_do_update(
        index_elements=["telegram_user_id"],
        set_=dict(
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
    )

    await db.execute(stmt)
    await db.commit()

    # Fetch and return the user
    return await get_user_by_telegram_id(db, telegram_user_id)


async def get_payment_by_body_hash(
    db: AsyncSession,
    body_sha256: str
) -> Optional[models.Payment]:
    """Get payment by body hash (idempotency check)"""
    result = await db.execute(
        select(models.Payment).where(models.Payment.body_sha256 == body_sha256)
    )
    return result.scalar_one_or_none()


async def create_payment(
    db: AsyncSession,
    event_name: str,
    user_id: int,
    telegram_user_id: int,
    raw_body: dict,
    signature: str,
    body_sha256: str,
    product_id: Optional[int] = None,
    amount: Optional[float] = None,
    currency: str = "RUB",
    expires_at: Optional[str] = None,
) -> models.Payment:
    """Create a new payment record"""
    # Parse expires_at if provided
    expires_at_dt = None
    if expires_at:
        try:
            expires_at_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    payment = models.Payment(
        provider="tribute",
        event_name=event_name,
        user_id=user_id,
        telegram_user_id=telegram_user_id,
        product_id=product_id,
        amount=amount,
        currency=currency,
        expires_at=expires_at_dt,
        raw_body=raw_body,
        signature=signature,
        body_sha256=body_sha256,
    )

    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def get_subscription(
    db: AsyncSession,
    user_id: int,
    subscription_id: int
) -> Optional[models.Subscription]:
    """Get subscription by user_id and subscription_id"""
    result = await db.execute(
        select(models.Subscription).where(
            models.Subscription.user_id == user_id,
            models.Subscription.subscription_id == subscription_id
        )
    )
    return result.scalar_one_or_none()


async def upsert_subscription(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    period: Optional[str] = None,
    status: str = "active",
    expires_at: Optional[str] = None,
) -> models.Subscription:
    """Insert or update subscription"""
    # Parse expires_at if provided
    expires_at_dt = None
    if expires_at:
        try:
            expires_at_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    stmt = sqlite_upsert(models.Subscription).values(
        user_id=user_id,
        subscription_id=subscription_id,
        period=period,
        status=status,
        expires_at=expires_at_dt,
        last_event_at=datetime.utcnow(),
    )

    # On conflict, update status, expires_at, last_event_at
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "subscription_id"],
        set_=dict(
            period=period,
            status=status,
            expires_at=expires_at_dt,
            last_event_at=datetime.utcnow(),
        )
    )

    await db.execute(stmt)
    await db.commit()

    # Fetch and return the subscription
    return await get_subscription(db, user_id, subscription_id)


async def update_subscription_status(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    status: str
) -> Optional[models.Subscription]:
    """Update subscription status"""
    subscription = await get_subscription(db, user_id, subscription_id)
    if not subscription:
        return None

    subscription.status = status
    subscription.last_event_at = datetime.utcnow()

    await db.commit()
    await db.refresh(subscription)
    return subscription


async def create_webhook_event(
    db: AsyncSession,
    name: str,
    body_sha256: str,
    sent_at: Optional[str] = None,
    raw_body: Optional[dict] = None,
) -> models.WebhookEvent:
    """Create webhook event record"""
    # Parse sent_at if provided
    sent_at_dt = None
    if sent_at:
        try:
            sent_at_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    event = models.WebhookEvent(
        name=name,
        body_sha256=body_sha256,
        sent_at=sent_at_dt,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def mark_webhook_processed(
    db: AsyncSession,
    event_id: int,
    error: Optional[str] = None,
) -> None:
    """Mark webhook event as processed"""
    result = await db.execute(
        select(models.WebhookEvent).where(models.WebhookEvent.id == event_id)
    )
    event = result.scalar_one_or_none()

    if event:
        event.processed_at = datetime.utcnow()
        event.status_code = 200 if error is None else 500
        event.error = error
        await db.commit()

