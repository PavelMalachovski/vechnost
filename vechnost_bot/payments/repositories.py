"""Repository layer for database operations."""

import logging
from datetime import datetime

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..compat import TOTAL_QUESTIONS
from .models import (
    AnalyticsEvent,
    Certificate,
    CompatTest,
    JobRun,
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
        can_message: bool | None = None,
    ) -> User:
        """Create or update user.

        `can_message=True` from the bot's own handlers: someone writing to
        the bot can be written to (see `User.can_message`). The payment
        webhook leaves it alone, since a purchase says nothing about a chat.
        """
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
            if can_message is not None:
                user.can_message = can_message
            logger.info(f"Updated user: {telegram_user_id}")
        else:
            # Create new user
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language=language,
                can_message=True if can_message is None else can_message,
            )
            session.add(user)
            logger.info(f"Created new user: {telegram_user_id}")

        await session.flush()
        return user

    @staticmethod
    async def ensure(
        session: AsyncSession,
        telegram_user_id: int,
        first_name: str | None = None,
        username: str | None = None,
        last_name: str | None = None,
        language: str | None = None,
    ) -> User:
        """The user's row, made if missing and its names brought up to date.

        One INSERT that does nothing on a conflict, not a read followed by a
        write: the bot's /start, the Mini App's boot and a join can each be
        the first to see a new person, and at once. `create_or_update` read
        first, so the second of two lost the race to the unique constraint.
        """
        bind = session.bind
        assert bind is not None, "get_db() always binds its sessions"
        if bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        await session.execute(
            insert(User)
            .values(
                telegram_user_id=telegram_user_id,
                first_name=first_name,
                username=username,
                last_name=last_name,
                language=language,
                daily_card_opt_out=False,
                created_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["telegram_user_id"])
        )
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        assert user is not None
        for field, value in (
            ("first_name", first_name), ("username", username),
            ("last_name", last_name), ("language", language),
        ):
            if value is not None and getattr(user, field) != value:
                setattr(user, field, value)
        await session.flush()
        return user

    @staticmethod
    async def pair(session: AsyncSession, one: int, other: int) -> None:
        """Make two people each other's partner, both ways, as of now."""
        if one == other:
            return
        now = datetime.utcnow()
        for user_id, partner_id in ((one, other), (other, one)):
            await session.execute(
                update(User)
                .where(User.telegram_user_id == user_id)
                .values(partner_telegram_user_id=partner_id, partner_since=now)
            )
        await session.flush()

    @staticmethod
    async def partner_of(session: AsyncSession, telegram_user_id: int) -> User | None:
        """The person this user last played with, if they are still here."""
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if not user or user.partner_telegram_user_id is None:
            return None
        return await UserRepository.get_by_telegram_id(session, user.partner_telegram_user_id)

    @staticmethod
    async def record_invite(
        session: AsyncSession, telegram_user_id: int, inviter_id: int
    ) -> bool:
        """Credit the person whose invite link seated a newcomer. True when
        it counted.

        The same newcomer rule as a `ref_` link (`record_referral`), and the
        same first-credit-wins, but it only counts: `referred_by` goes up in
        the inviter's /invite, and `referred_at` - the marker the referral
        price reads - stays unset. A partner invited into a game pays what
        everyone pays.
        """
        from ..referrals import joined_recently

        if telegram_user_id == inviter_id:
            return False
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if not user or user.referred_by is not None or user.referred_at is not None:
            return False
        if not joined_recently(user.created_at, datetime.utcnow()):
            return False
        if await UserRepository.has_history(session, user):
            return False
        user.referred_by = inviter_id
        await session.flush()
        logger.info(f"User {telegram_user_id} was invited by {inviter_id}")
        return True

    @staticmethod
    async def set_daily_card_opt_out(
        session: AsyncSession, telegram_user_id: int, opt_out: bool
    ) -> None:
        """Set whether the user receives the daily card push.

        Creates the row when it is missing rather than silently doing
        nothing: an unsubscribe that no-ops is the worst failure mode a
        «Больше не присылать» button can have, and a resubscribe from a
        user the bot has never written down should stick too.
        """
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if user is None:
            user = User(telegram_user_id=telegram_user_id, daily_card_opt_out=opt_out)
            session.add(user)
        else:
            user.daily_card_opt_out = opt_out
        await session.flush()

    @staticmethod
    async def set_can_message(
        session: AsyncSession, telegram_user_id: int, can_message: bool
    ) -> None:
        """Record whether the bot can start a conversation with this user.

        Only an existing row: a send that failed for somebody the bot never
        wrote down has nothing to mark.
        """
        await session.execute(
            update(User)
            .where(User.telegram_user_id == telegram_user_id)
            .values(can_message=can_message)
        )

    @staticmethod
    async def get_daily_card_recipients(
        session: AsyncSession, after: int | None = None, limit: int | None = None
    ) -> list[User]:
        """Users who haven't opted out of the daily card and whom the bot
        can write to, by Telegram id.

        In id order, so a run can go a page at a time (`limit`) and be
        resumed after the last person it reached (`after`): the list is
        read as the run goes, and somebody who opts out mid-run is skipped.
        """
        query = select(User).where(
            User.daily_card_opt_out.is_(False), User.can_message.is_(True)
        )
        if after is not None:
            query = query.where(User.telegram_user_id > after)
        query = query.order_by(User.telegram_user_id)
        if limit is not None:
            query = query.limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_referral_code(
        session: AsyncSession, code: str
    ) -> User | None:
        """The user who hands out this code."""
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_referral_code(
        session: AsyncSession, telegram_user_id: int
    ) -> str | None:
        """This user's code, minted on the first ask and stable after.

        Derives a candidate from the user id and salts the seed again on a
        collision, so two accounts never share a code and the loop always
        terminates on a keyspace of 32^6.
        """
        from ..referrals import code_from_seed

        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if not user:
            return None
        if user.referral_code:
            return user.referral_code

        for attempt in range(20):
            seed = f"{telegram_user_id}:{attempt}"
            candidate = code_from_seed(seed)
            taken = await UserRepository.get_by_referral_code(session, candidate)
            if taken is None or taken.id == user.id:
                user.referral_code = candidate
                await session.flush()
                return candidate

        logger.error(f"Could not mint a referral code for {telegram_user_id}")
        return None

    @staticmethod
    async def has_history(session: AsyncSession, user: User) -> bool:
        """Whether this user has ever bought or redeemed anything.

        Any `payments` row (the journal: a purchase, a gift, a refund), any
        `subscriptions` row whatever its status, or a certificate they
        activated. Such a person is a customer already, whatever the age of
        their row, and an invitation did not bring them in.
        """
        for statement in (
            select(Payment.id).where(Payment.telegram_user_id == user.telegram_user_id),
            select(Subscription.id).where(Subscription.user_id == user.id),
            select(Certificate.id).where(
                Certificate.used_by_telegram_user_id == user.telegram_user_id
            ),
        ):
            if (await session.execute(statement.limit(1))).first() is not None:
                return True
        return False

    @staticmethod
    async def record_referral(
        session: AsyncSession, telegram_user_id: int, code: str
    ) -> bool:
        """Credit an invitation. True when it counted, False when it did not.

        Only a newcomer can be invited: a user whose row is younger than
        `referrals.NEW_USER_WINDOW` - in practice the one this same /start
        just created - and who has bought or redeemed nothing. For anyone
        who was already here the link changes nothing. Also refused for a
        user who was already invited (the credit belongs to whoever invited
        them first, and stays theirs after that person is erased), for a
        code nobody owns, and for anyone following their own link.
        """
        from ..referrals import joined_recently

        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        # `referred_by` alone is an invitation into a game (`record_invite`),
        # which came first and keeps the credit.
        if not user or user.referred_at is not None or user.referred_by is not None:
            return False
        now = datetime.utcnow()
        if not joined_recently(user.created_at, now):
            return False
        if await UserRepository.has_history(session, user):
            return False

        referrer = await UserRepository.get_by_referral_code(session, code)
        if not referrer or referrer.telegram_user_id == telegram_user_id:
            return False

        user.referred_by = referrer.telegram_user_id
        user.referred_at = now
        await session.flush()
        logger.info(f"User {telegram_user_id} was referred by {referrer.telegram_user_id}")
        return True

    @staticmethod
    async def count_referrals(session: AsyncSession, telegram_user_id: int) -> int:
        """How many people came in on this user's link."""
        result = await session.execute(
            select(User).where(User.referred_by == telegram_user_id)
        )
        return len(list(result.scalars().all()))

    @staticmethod
    async def is_referred(session: AsyncSession, telegram_user_id: int) -> bool:
        """Whether this user came in on an invitation.

        Read from `referred_at`, never from `referred_by`: the link to the
        inviter is cleared when the inviter is erased, and the discount it
        promised is not theirs to take back.
        """
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        return bool(user and user.referred_at is not None)

    @staticmethod
    async def erase(session: AsyncSession, telegram_user_id: int) -> dict[str, int]:
        """Delete everything the bot holds about one person. Returns counts.

        The user row goes with its payments and subscriptions (the money
        side lives at Tribute, and a journal keyed by a person is still a
        record of that person). A room, a test or a board the user sat in
        is one row shared with a partner and goes too: the answers in it
        are half theirs, and consent to keep them has to be unanimous, the
        same rule `DELETE /api/compat/{code}` follows. A certificate the
        user redeemed stays spent but forgets who spent it, so the code
        cannot be redeemed again. A gift certificate the user bought keeps
        the Tribute purchase id it was issued for: that names a purchase,
        not a person, and is what lets a later refund of the gift still
        revoke it. Anyone this user invited keeps their discount and loses
        the link to who invited them: `referred_by` is cleared,
        `referred_at` - the marker the discount reads - stays. Whoever had
        them as a partner loses that link too. Every
        analytics event of the user goes as well: counted, it is still a
        record of what they did.
        """
        from sqlalchemy import update as _update

        removed: dict[str, int] = {}

        for name, model in (
            ("rooms", Room),
            ("compat_tests", CompatTest),
            ("games", Steps69Game),
        ):
            result = await session.execute(
                delete(model).where(
                    or_(
                        model.creator_telegram_user_id == telegram_user_id,
                        model.guest_telegram_user_id == telegram_user_id,
                    )
                )
            )
            removed[name] = result.rowcount or 0

        result = await session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.telegram_user_id == telegram_user_id)
        )
        removed["events"] = result.rowcount or 0

        result = await session.execute(
            _update(Certificate)
            .where(Certificate.used_by_telegram_user_id == telegram_user_id)
            .values(used_by_telegram_user_id=None)
        )
        removed["certificates_unlinked"] = result.rowcount or 0

        result = await session.execute(
            _update(User)
            .where(User.referred_by == telegram_user_id)
            .values(referred_by=None)
        )
        removed["referrals_unlinked"] = result.rowcount or 0

        # Whoever played with them forgets them too: their partner link is
        # a record of this person.
        result = await session.execute(
            _update(User)
            .where(User.partner_telegram_user_id == telegram_user_id)
            .values(partner_telegram_user_id=None, partner_since=None)
        )
        removed["partners_unlinked"] = result.rowcount or 0

        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        if user is None:
            removed["user"] = 0
        else:
            # Through the session, so the ORM cascade takes payments and
            # subscriptions with it.
            await session.delete(user)
            removed["user"] = 1
        await session.flush()
        logger.info(f"Erased user {telegram_user_id}: {removed}")
        return removed

    @staticmethod
    async def get_all(session: AsyncSession) -> list[User]:
        """Every registered user the bot can write to, oldest first.

        Deliberately does not honour `daily_card_opt_out`: that flag is a
        choice about the daily prompt, not consent withdrawn from the bot,
        and the one caller is an announcement about the product itself.
        Anything recurring belongs in `get_daily_card_recipients`. It does
        skip `can_message` false: a send there can only fail.
        """
        result = await session.execute(
            select(User).where(User.can_message.is_(True)).order_by(User.id)
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


# Statuses of a subscription row that grant access while unexpired, and the
# one that grants it only until `expires_at`: renewal switched off, the
# period paid for still running.
GRANTING_STATUSES = ("active", "trialing")
CANCELED = "canceled"


class SubscriptionRepository:
    """Repository for Subscription operations."""

    @staticmethod
    async def get_by_user_and_subscription_id(
        session: AsyncSession, user_id: int, subscription_id: int, for_update: bool = False
    ) -> Subscription | None:
        """Get subscription by user and subscription ID.

        `for_update` locks the row: a webhook reads its `last_event_at` to
        decide whether the event is newer, then writes it, and two
        deliveries for one purchase can arrive together.
        """
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.subscription_id == subscription_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        session: AsyncSession,
        user_id: int,
        subscription_id: int,
        period: str,
        status: str,
        expires_at: datetime | None,
        last_event_at: datetime | None = None,
    ) -> Subscription:
        """Create or update subscription. No expiry is a lifetime purchase."""
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
    async def revoke_all_for_user(
        session: AsyncSession,
        user_id: int,
        status: str = "refunded",
        when: datetime | None = None,
    ) -> int:
        """Close every row of this user that still grants access. Returns how many.

        The fallback for a refund that names no row the user has - an older
        row filed under a different key, or a refund that names the product
        rather than the purchase: a refund with no effect is worse than one
        with too much, since the money went back and the deck stayed open. A
        cancelled subscription still inside its paid period is one of these
        rows. `last_event_at` only ever moves forward here.
        """
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status.in_([*GRANTING_STATUSES, CANCELED]))
            .with_for_update()
        )
        rows = list(result.scalars().all())
        stamp = when or datetime.utcnow()
        for row in rows:
            row.status = status
            row.last_event_at = max(row.last_event_at, stamp)
        await session.flush()
        if rows:
            logger.info(f"Revoked {len(rows)} subscription row(s) for user {user_id}")
        return len(rows)

    @staticmethod
    async def get_active_subscriptions_for_user(
        session: AsyncSession, user_id: int
    ) -> list[Subscription]:
        """The rows that grant this user access now.

        An active row until it expires (a lifetime purchase never does),
        and a cancelled subscription until the end of the period already
        paid for: a cancellation switches the renewal off, it does not take
        back what was bought (backend audit B-09). A cancelled row with no
        expiry is never access - the code that cancelled rows that way was
        also recording chargebacks as cancellations.
        """
        now = datetime.utcnow()
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(
                or_(
                    and_(
                        Subscription.status.in_(GRANTING_STATUSES),
                        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
                    ),
                    and_(Subscription.status == CANCELED, Subscription.expires_at > now),
                )
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
    async def get_by_event_key(
        session: AsyncSession, event_key: str
    ) -> WebhookEvent | None:
        """The delivery on record for this event, whatever its body said."""
        result = await session.execute(
            select(WebhookEvent).where(WebhookEvent.event_key == event_key)
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
        event_key: str | None = None,
    ) -> WebhookEvent:
        """Create webhook event record."""
        webhook_event = WebhookEvent(
            name=name,
            sent_at=sent_at,
            body_sha256=body_sha256,
            event_key=event_key,
            status_code=status_code,
            processed_at=processed_at,
            error=error,
        )
        session.add(webhook_event)
        await session.flush()
        logger.info(f"Created webhook event: {name} (status: {status_code})")
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
    async def get_by_purchase(
        session: AsyncSession, purchase_id: str, for_update: bool = False
    ) -> Certificate | None:
        """The certificate a Tribute purchase paid for, if one was issued."""
        stmt = select(Certificate).where(Certificate.purchase_id == purchase_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
        purchase_id: str | None = None,
    ) -> Certificate:
        """Create a new certificate, for the purchase that paid for it if any."""
        certificate = Certificate(code=code, purchase_id=purchase_id)
        session.add(certificate)
        await session.flush()
        # The id, never the code: a code in the log is lifetime access to
        # whoever can read the log.
        logger.info(f"Created certificate #{certificate.id}")
        return certificate

    @staticmethod
    async def claim(
        session: AsyncSession, code: str, telegram_user_id: int
    ) -> Certificate | None:
        """Take an unused certificate for this user, atomically.

        One UPDATE whose WHERE clause carries the condition, so two people
        redeeming the same code at the same moment cannot both read
        `is_used = false` and both mark it: the database decides, exactly
        one row changes, and the loser gets None. It replaces a read of the
        row followed by a write to it, the way activation used to work.
        """
        result = await session.execute(
            update(Certificate)
            .where(Certificate.code == code)
            .where(Certificate.is_used == False)  # noqa: E712
            # A refund landing between the caller's check and this UPDATE.
            .where(Certificate.revoked_at.is_(None))
            .values(
                is_used=True,
                used_by_telegram_user_id=telegram_user_id,
                used_at=datetime.utcnow(),
            )
        )
        if result.rowcount != 1:
            return None
        certificate = await CertificateRepository.get_by_code(session, code)
        if certificate is not None:
            await session.refresh(certificate)
            logger.info(
                f"Claimed certificate #{certificate.id} for user {telegram_user_id}"
            )
        return certificate

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
    async def get_by_code(
        session: AsyncSession, code: str, for_update: bool = False
    ) -> Room | None:
        """Get room by its invite code; `for_update` locks the row (see /advance)."""
        stmt = select(Room).where(Room.code == code)
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
        # Rooms, tests and games are logged by row id, never by code: the
        # code is the seat itself for as long as the game is open.
        logger.info(f"Created room #{room.id} by {creator_telegram_user_id}")
        return room

    @staticmethod
    async def seat_guest(
        session: AsyncSession, room: Room, telegram_user_id: int, name: str | None
    ) -> bool:
        """Take the second seat, atomically. False when somebody else has it.

        The WHERE clause carries the emptiness check, so two partners who
        open the same link at once cannot both read an empty seat and both
        write themselves into it with the last one winning silently. The
        instance is refreshed either way, so the caller sees who sits there.
        """
        result = await session.execute(
            update(Room)
            .where(Room.id == room.id)
            .where(Room.guest_telegram_user_id.is_(None))
            .values(
                guest_telegram_user_id=telegram_user_id,
                guest_name=name,
                updated_at=datetime.utcnow(),
            )
        )
        await session.refresh(room)
        return result.rowcount == 1


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
        move. SQLite ignores the clause; there every transaction begins
        IMMEDIATE instead (`database._sqlite_file_engine`), which takes the
        same turns over the whole file.
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
        creator_piece: str,
    ) -> Steps69Game:
        """Start a game with both pieces on cell 1 and nothing spent yet."""
        game = Steps69Game(
            code=code,
            mode=mode,
            creator_telegram_user_id=creator_telegram_user_id,
            creator_name=creator_name,
            creator_piece=creator_piece,
            used_jokers=[],
        )
        session.add(game)
        await session.flush()
        logger.info(f"Created steps69 game #{game.id} ({mode}) by {creator_telegram_user_id}")
        return game

    @staticmethod
    async def seat_guest(
        session: AsyncSession,
        game: Steps69Game,
        telegram_user_id: int,
        name: str | None,
        piece: str,
    ) -> bool:
        """Take the second seat, atomically. See `RoomRepository.seat_guest`."""
        result = await session.execute(
            update(Steps69Game)
            .where(Steps69Game.id == game.id)
            .where(Steps69Game.guest_telegram_user_id.is_(None))
            .values(
                guest_telegram_user_id=telegram_user_id,
                guest_name=name,
                guest_piece=piece,
                updated_at=datetime.utcnow(),
            )
        )
        await session.refresh(game)
        return result.rowcount == 1

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
        session: AsyncSession,
        idle_since: datetime,
        give_up_before: datetime,
        after_id: int | None = None,
    ) -> list[Steps69Game]:
        """Games abandoned mid-board and not yet nudged about.

        Bounded on both sides on purpose: `idle_since` keeps the push off a
        pair who are playing right now, and `give_up_before` stops the job
        from resurrecting a game from two months ago that nobody meant to
        finish. A game that has never been rolled is not stalled, it was
        never started. In id order, and past `after_id` when given, so a
        nudge run taken over after a restart carries on after the last game
        it reached.
        """
        query = select(Steps69Game).where(
            Steps69Game.finished.is_(False),
            (Steps69Game.creator_turns + Steps69Game.guest_turns) > 0,
            Steps69Game.resume_notified_at.is_(None),
            Steps69Game.updated_at < idle_since,
            Steps69Game.updated_at > give_up_before,
        )
        if after_id is not None:
            query = query.where(Steps69Game.id > after_id)
        result = await session.execute(query.order_by(Steps69Game.id))
        return list(result.scalars().all())

    @staticmethod
    async def mark_resume_notified(
        session: AsyncSession, game_ids: list[int], when: datetime
    ) -> None:
        """Record that a stalled-game nudge actually reached these games.

        Called after the sends, not before: a game flagged before anyone
        was reached is a game whose pair never hears about it. The nudge
        marks each game the moment it is reached, so a run cut short is
        resumed without messaging those pairs again.

        One UPDATE that sets `updated_at` to itself. Assigning the flag
        through the ORM fired the column's `onupdate`, so a nudge counted as
        activity: the retention clock for an abandoned board restarted, and
        `/mine` could offer an old nudged game over a newer one.
        """
        if not game_ids:
            return
        await session.execute(
            update(Steps69Game)
            .where(Steps69Game.id.in_(game_ids))
            .values(resume_notified_at=when, updated_at=Steps69Game.updated_at)
        )
        await session.flush()


class RetentionRepository:
    """Deleting what nobody is coming back for.

    Every row here is about somebody's sex life. A room is unreachable the
    moment its TTL passes and the row is then only a record nobody asked us
    to keep; an unfinished compatibility test or an abandoned board past
    three months is the same. Finished tests and finished games are left
    alone deliberately: those are meant to be re-read months later, and that
    is the whole reason they have no TTL.
    """

    @staticmethod
    async def delete_old_job_runs(session: AsyncSession, before: datetime) -> int:
        """Scheduled-job runs started before `before` (`jobs.KEEP`)."""
        result = await session.execute(
            delete(JobRun).where(JobRun.started_at < before)
        )
        return result.rowcount or 0

    @staticmethod
    async def delete_old_events(session: AsyncSession, before: datetime) -> int:
        """Analytics events that happened before `before` (`analytics.KEEP`)."""
        result = await session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.created_at < before)
        )
        return result.rowcount or 0

    @staticmethod
    async def delete_expired_rooms(session: AsyncSession, before: datetime) -> int:
        """Rooms last touched before `before`. They already 410 on read."""
        result = await session.execute(
            delete(Room).where(Room.updated_at < before)
        )
        return result.rowcount or 0

    @staticmethod
    async def delete_abandoned_compat_tests(
        session: AsyncSession, before: datetime
    ) -> int:
        """Unfinished tests nobody has touched since `before`.

        `finished_at is None` is the whole condition that matters: a
        completed test is a result the pair may come back to, and deleting
        one because it is old would take away the thing they answered eighty
        questions for.
        """
        result = await session.execute(
            delete(CompatTest).where(
                CompatTest.finished_at.is_(None),
                CompatTest.updated_at < before,
            )
        )
        return result.rowcount or 0

    @staticmethod
    async def delete_abandoned_games(
        session: AsyncSession, before: datetime
    ) -> int:
        """Unfinished boards nobody has touched since `before`.

        The resume nudge gives up after a week; three months later the pair
        are not coming back to that board, and a finished one is kept.
        """
        result = await session.execute(
            delete(Steps69Game).where(
                Steps69Game.finished.is_(False),
                Steps69Game.updated_at < before,
            )
        )
        return result.rowcount or 0


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
        silently vanishes. SQLite ignores the clause; there every transaction
        begins IMMEDIATE instead (`database._sqlite_file_engine`), which takes
        the same turns over the whole file.
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
        logger.info(f"Created compat test #{test.id} by {creator_telegram_user_id}")
        return test

    @staticmethod
    async def seat_guest(
        session: AsyncSession, test: CompatTest, telegram_user_id: int, name: str | None
    ) -> bool:
        """Take the second seat, atomically. See `RoomRepository.seat_guest`.

        Also writes the pair key, which is what a retake later supersedes
        by: it belongs to the moment the pair became a pair.
        """
        low, high = sorted((test.creator_telegram_user_id, telegram_user_id))
        result = await session.execute(
            update(CompatTest)
            .where(CompatTest.id == test.id)
            .where(CompatTest.guest_telegram_user_id.is_(None))
            .values(
                guest_telegram_user_id=telegram_user_id,
                guest_name=name,
                pair_key=f"{low}:{high}",
                updated_at=datetime.utcnow(),
            )
        )
        await session.refresh(test)
        return result.rowcount == 1

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
        Delete this pair's older sessions.

        Retaking replaces the previous result rather than adding to a history,
        so the answers behind a superseded result do not linger in the
        database. Older only: a pair with two tests open - a second invite
        sent by mistake, or the old one finished while a retake was under
        way - used to lose the *newer* one, answers and all, the moment the
        older one completed, and the partner answering it got a 404.
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
                CompatTest.pair_key == pair_key, CompatTest.id < keep_id
            )
        )
        await session.flush()
        return result.rowcount or 0
