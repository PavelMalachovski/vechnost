"""Repository layer for database operations."""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, Product, Payment, Subscription, WebhookEvent

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User operations."""

    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession, telegram_user_id: int
    ) -> Optional[User]:
        """Get user by Telegram ID."""
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_or_update(
        session: AsyncSession,
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Create or update user."""
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)

        if user:
            # Update existing user
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            logger.info(f"Updated user: {telegram_user_id}")
        else:
            # Create new user
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            session.add(user)
            logger.info(f"Created new user: {telegram_user_id}")

        await session.flush()
        return user


class ProductRepository:
    """Repository for Product operations."""

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        """Get product by ID."""
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Product]:
        """Get all products."""
        result = await session.execute(select(Product).order_by(Product.amount))
        return list(result.scalars().all())

    @staticmethod
    async def upsert(
        session: AsyncSession,
        product_id: int,
        type: str,
        name: str,
        amount: int,
        currency: str,
        stars_amount: Optional[int] = None,
        t_link: Optional[str] = None,
        web_link: Optional[str] = None,
    ) -> Product:
        """Create or update product."""
        product = await ProductRepository.get_by_id(session, product_id)

        if product:
            # Update existing product
            product.type = type
            product.name = name
            product.amount = amount
            product.currency = currency
            product.stars_amount = stars_amount
            product.t_link = t_link
            product.web_link = web_link
            product.updated_at = datetime.utcnow()
            logger.info(f"Updated product: {product_id}")
        else:
            # Create new product
            product = Product(
                id=product_id,
                type=type,
                name=name,
                amount=amount,
                currency=currency,
                stars_amount=stars_amount,
                t_link=t_link,
                web_link=web_link,
            )
            session.add(product)
            logger.info(f"Created new product: {product_id}")

        await session.flush()
        return product


class PaymentRepository:
    """Repository for Payment operations."""

    @staticmethod
    async def get_by_body_sha256(
        session: AsyncSession, body_sha256: str
    ) -> Optional[Payment]:
        """Get payment by body SHA256."""
        result = await session.execute(
            select(Payment).where(Payment.body_sha256 == body_sha256)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        provider: str,
        event_name: str,
        user_id: int,
        telegram_user_id: int,
        amount: int,
        currency: str,
        raw_body: dict,
        signature: str,
        body_sha256: str,
        product_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> Payment:
        """Create payment record."""
        payment = Payment(
            provider=provider,
            event_name=event_name,
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            product_id=product_id,
            amount=amount,
            currency=currency,
            expires_at=expires_at,
            raw_body=raw_body,
            signature=signature,
            body_sha256=body_sha256,
        )
        session.add(payment)
        await session.flush()
        logger.info(f"Created payment for user {telegram_user_id}: {event_name}")
        return payment

    @staticmethod
    async def get_active_payments_for_user(
        session: AsyncSession, telegram_user_id: int
    ) -> List[Payment]:
        """Get active (non-expired) payments for user."""
        now = datetime.utcnow()
        result = await session.execute(
            select(Payment)
            .where(Payment.telegram_user_id == telegram_user_id)
            .where(
                or_(Payment.expires_at.is_(None), Payment.expires_at > now)
            )
        )
        return list(result.scalars().all())


class SubscriptionRepository:
    """Repository for Subscription operations."""

    @staticmethod
    async def get_by_user_and_subscription_id(
        session: AsyncSession, user_id: int, subscription_id: int
    ) -> Optional[Subscription]:
        """Get subscription by user and subscription ID."""
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.subscription_id == subscription_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        session: AsyncSession,
        user_id: int,
        subscription_id: int,
        period: str,
        status: str,
        expires_at: datetime,
        last_event_at: Optional[datetime] = None,
    ) -> Subscription:
        """Create or update subscription."""
        subscription = await SubscriptionRepository.get_by_user_and_subscription_id(
            session, user_id, subscription_id
        )

        if last_event_at is None:
            last_event_at = datetime.utcnow()

        if subscription:
            # Update existing subscription
            subscription.period = period
            subscription.status = status
            subscription.expires_at = expires_at
            subscription.last_event_at = last_event_at
            logger.info(
                f"Updated subscription {subscription_id} for user {user_id}: {status}"
            )
        else:
            # Create new subscription
            subscription = Subscription(
                user_id=user_id,
                subscription_id=subscription_id,
                period=period,
                status=status,
                expires_at=expires_at,
                last_event_at=last_event_at,
            )
            session.add(subscription)
            logger.info(
                f"Created subscription {subscription_id} for user {user_id}: {status}"
            )

        await session.flush()
        return subscription

    @staticmethod
    async def get_active_subscriptions_for_user(
        session: AsyncSession, user_id: int
    ) -> List[Subscription]:
        """Get active subscriptions for user (including lifetime subscriptions)."""
        now = datetime.utcnow()
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status.in_(["active", "trialing"]))
            .where(
                (Subscription.expires_at.is_(None)) |  # Lifetime subscription
                (Subscription.expires_at > now)  # Or not expired yet
            )
        )
        return list(result.scalars().all())


class WebhookEventRepository:
    """Repository for WebhookEvent operations."""

    @staticmethod
    async def get_by_body_sha256(
        session: AsyncSession, body_sha256: str
    ) -> Optional[WebhookEvent]:
        """Get webhook event by body SHA256."""
        result = await session.execute(
            select(WebhookEvent).where(WebhookEvent.body_sha256 == body_sha256)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        sent_at: datetime,
        body_sha256: str,
        status_code: int,
        processed_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> WebhookEvent:
        """Create webhook event record."""
        webhook_event = WebhookEvent(
            name=name,
            sent_at=sent_at,
            body_sha256=body_sha256,
            status_code=status_code,
            processed_at=processed_at,
            error=error,
        )
        session.add(webhook_event)
        await session.flush()
        logger.info(f"Created webhook event: {name} (status: {status_code})")
        return webhook_event

    @staticmethod
    async def update_status(
        session: AsyncSession,
        webhook_event: WebhookEvent,
        status_code: int,
        processed_at: datetime,
        error: Optional[str] = None,
    ) -> WebhookEvent:
        """Update webhook event status."""
        webhook_event.status_code = status_code
        webhook_event.processed_at = processed_at
        webhook_event.error = error
        await session.flush()
        return webhook_event

