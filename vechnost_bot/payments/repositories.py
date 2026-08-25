"""Repository layer for database operations."""

import logging
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..compat import TOTAL_QUESTIONS
from .models import (
    Certificate,
    CompatTest,
    Payment,
    Product,
    Room,
    Steps69Game,
    Subscription,
    User,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User operations."""

    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession, telegram_user_id: int
    ) -> User | None:
        """Get user by Telegram ID."""
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_or_update(
        session: AsyncSession,
        telegram_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language: str | None = None,
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
            if language is not None:
                user.language = language
            logger.info(f"Updated user: {telegram_user_id}")
        else:
            # Create new user
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language=language,
            )
            session.add(user)
            logger.info(f"Created new user: {telegram_user_id}")

        await session.flush()
        return user

    @staticmethod
    async def set_daily_card_opt_out(
        session: AsyncSession, telegram_user_id: int, opt_out: bool
    ) -> None:
        """Set whether the user receives the daily card push."""
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if user:
            user.daily_card_opt_out = opt_out
            await session.flush()

    @staticmethod
    async def get_daily_card_recipients(session: AsyncSession) -> list[User]:
        """All users who haven't opted out of the daily card."""
        result = await session.execute(
            select(User).where(User.daily_card_opt_out.is_(False))
        )
        return list(result.scalars().all())


class ProductRepository:
    """Repository for Product operations."""

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Product | None:
        """Get product by ID."""
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(session: AsyncSession) -> list[Product]:
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
        stars_amount: int | None = None,
        t_link: str | None = None,
        web_link: str | None = None,
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
    ) -> Payment | None:
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
        product_id: int | None = None,
        expires_at: datetime | None = None,
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
    ) -> list[Payment]:
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
    ) -> Subscription | None:
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
        last_event_at: datetime | None = None,
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
    ) -> list[Subscription]:
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
    ) -> WebhookEvent | None:
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
        processed_at: datetime | None = None,
        error: str | None = None,
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
        error: str | None = None,
    ) -> WebhookEvent:
        """Update webhook event status."""
        webhook_event.status_code = status_code
        webhook_event.processed_at = processed_at
        webhook_event.error = error
        await session.flush()
        return webhook_event


class CertificateRepository:
    """Repository for Certificate operations."""

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str) -> Certificate | None:
        """Get certificate by code."""
        result = await session.execute(
            select(Certificate).where(Certificate.code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
    ) -> Certificate:
        """Create a new certificate."""
        certificate = Certificate(code=code)
        session.add(certificate)
        await session.flush()
        logger.info(f"Created certificate with code: {code}")
        return certificate

    @staticmethod
    async def mark_as_used(
        session: AsyncSession,
        certificate: Certificate,
        telegram_user_id: int,
    ) -> Certificate:
        """Mark certificate as used by a user."""
        certificate.is_used = True
        certificate.used_by_telegram_user_id = telegram_user_id
        certificate.used_at = datetime.utcnow()
        await session.flush()
        logger.info(
            f"Marked certificate {certificate.code} as used by user {telegram_user_id}"
        )
        return certificate

    @staticmethod
    async def get_all_unused(session: AsyncSession) -> list[Certificate]:
        """Get all unused certificates."""
        result = await session.execute(
            select(Certificate)
            .where(Certificate.is_used == False)  # noqa: E712
            .order_by(Certificate.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_all(session: AsyncSession) -> list[Certificate]:
        """Get all certificates."""
        result = await session.execute(
            select(Certificate).order_by(Certificate.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_user(
        session: AsyncSession, telegram_user_id: int
    ) -> list[Certificate]:
        """Get all certificates used by a specific user."""
        result = await session.execute(
            select(Certificate).where(
                Certificate.used_by_telegram_user_id == telegram_user_id
            )
        )
        return list(result.scalars().all())



class RoomRepository:
    """Repository for couple-mode Room operations."""

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str) -> Room | None:
        """Get room by its invite code."""
        result = await session.execute(select(Room).where(Room.code == code))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
        creator_telegram_user_id: int,
        creator_name: str | None,
        theme: str,
        level: int | None,
        content_type: str,
        card_order: list,
    ) -> Room:
        """Create a new room."""
        room = Room(
            code=code,
            creator_telegram_user_id=creator_telegram_user_id,
            creator_name=creator_name,
            theme=theme,
            level=level,
            content_type=content_type,
            card_order=card_order,
        )
        session.add(room)
        await session.flush()
        logger.info(f"Created room {code} by {creator_telegram_user_id}")
        return room


class Steps69Repository:
    """Repository for «69 ступеней» games."""

    @staticmethod
    async def get_by_code(
        session: AsyncSession, code: str, for_update: bool = False
    ) -> Steps69Game | None:
        """Get a game by its invite code.

        `for_update` takes a row lock, which rolling the dice needs: a roll
        is a read-modify-write of position, turn count and the spent-joker
        list, and both partners' clients poll the same row. Without it, two
        rolls landing together on READ COMMITTED would each read the same
        starting square and the second would overwrite the first, losing a
        move. SQLite ignores the clause; it has no concurrent writers.
        """
        stmt = select(Steps69Game).where(Steps69Game.code == code)
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
        creator_telegram_user_id: int,
        creator_name: str | None,
        mode: str,
    ) -> Steps69Game:
        """Start a game with the piece on cell 1 and nothing spent yet."""
        game = Steps69Game(
            code=code,
            mode=mode,
            creator_telegram_user_id=creator_telegram_user_id,
            creator_name=creator_name,
            used_jokers=[],
            reactions=[],
        )
        session.add(game)
        await session.flush()
        logger.info(f"Created steps69 game {code} ({mode}) by {creator_telegram_user_id}")
        return game

    @staticmethod
    async def delete(session: AsyncSession, game_id: int) -> None:
        """Delete one game outright."""
        await session.execute(delete(Steps69Game).where(Steps69Game.id == game_id))
        await session.flush()

    @staticmethod
    async def latest_unfinished_for(
        session: AsyncSession, telegram_user_id: int
    ) -> Steps69Game | None:
        """The caller's most recently touched game that is still in play."""
        result = await session.execute(
            select(Steps69Game)
            .where(
                or_(
                    Steps69Game.creator_telegram_user_id == telegram_user_id,
                    Steps69Game.guest_telegram_user_id == telegram_user_id,
                ),
                Steps69Game.finished.is_(False),
            )
            .order_by(Steps69Game.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def stalled(
        session: AsyncSession, idle_since: datetime, give_up_before: datetime
    ) -> list[Steps69Game]:
        """Games abandoned mid-board and not yet nudged about.

        Bounded on both sides on purpose: `idle_since` keeps the push off a
        pair who are playing right now, and `give_up_before` stops the job
        from resurrecting a game from two months ago that nobody meant to
        finish. A game that has never been rolled is not stalled, it was
        never started.
        """
        result = await session.execute(
            select(Steps69Game).where(
                Steps69Game.finished.is_(False),
                Steps69Game.turns > 0,
                Steps69Game.resume_notified_at.is_(None),
                Steps69Game.updated_at < idle_since,
                Steps69Game.updated_at > give_up_before,
            )
        )
        return list(result.scalars().all())


class CompatTestRepository:
    """Repository for compatibility-test sessions."""

    @staticmethod
    async def get_by_code(
        session: AsyncSession, code: str, for_update: bool = False
    ) -> CompatTest | None:
        """Get a session by its invite code.

        `for_update` takes a row lock, which `/answer` needs: it does a
        read-modify-write of the whole 40-element answer array, and a fast
        tapper has several POSTs in flight at once. Without the lock, on
        READ COMMITTED the second transaction reads the pre-update array and
        writes back a stale copy of everything but its own index — one answer
        silently vanishes. SQLite ignores the clause; it has no concurrent
        writers to protect against.
        """
        stmt = select(CompatTest).where(CompatTest.code == code)
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete(session: AsyncSession, test_id: int) -> None:
        """Delete one session outright, answers and all."""
        await session.execute(delete(CompatTest).where(CompatTest.id == test_id))
        await session.flush()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
        creator_telegram_user_id: int,
        creator_name: str | None,
    ) -> CompatTest:
        """Create a session with both answer sets empty."""
        test = CompatTest(
            code=code,
            creator_telegram_user_id=creator_telegram_user_id,
            creator_name=creator_name,
            creator_answers=[None] * TOTAL_QUESTIONS,
            guest_answers=[None] * TOTAL_QUESTIONS,
        )
        session.add(test)
        await session.flush()
        logger.info(f"Created compat test {code} by {creator_telegram_user_id}")
        return test

    @staticmethod
    async def latest_completed_for(
        session: AsyncSession, telegram_user_id: int
    ) -> CompatTest | None:
        """The caller's most recently completed session, as either participant."""
        result = await session.execute(
            select(CompatTest)
            .where(
                CompatTest.finished_at.is_not(None),
                or_(
                    CompatTest.creator_telegram_user_id == telegram_user_id,
                    CompatTest.guest_telegram_user_id == telegram_user_id,
                ),
            )
            .order_by(CompatTest.finished_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_superseded(
        session: AsyncSession, pair_key: str, keep_id: int
    ) -> int:
        """
        Delete this pair's other sessions.

        Retaking replaces the previous result rather than adding to a history,
        so the answers behind a superseded result do not linger in the
        database.
        """
        if pair_key is None:
            # SQLAlchemy compiles `Column == None` to `IS NULL`, not to a
            # predicate that matches nothing — every unpaired session (any
            # user whose guest hasn't joined yet) has a null pair_key. An
            # unpaired session has nothing to supersede, so the honest
            # answer is "deleted nothing", not an exception.
            return 0
        result = await session.execute(
            delete(CompatTest).where(
                CompatTest.pair_key == pair_key, CompatTest.id != keep_id
            )
        )
        await session.flush()
        return result.rowcount or 0
