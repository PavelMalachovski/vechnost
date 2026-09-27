"""Database models for payment system."""

import json
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    column,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator


class JSONEncodedDict(TypeDecorator):
    """Represents an immutable structure as a json-encoded string for SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert dict to JSON string when saving."""
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert JSON string to dict when loading."""
        if value is not None:
            value = json.loads(value)
        return value


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


def _partial(where: ColumnElement[bool]) -> dict[str, Any]:
    """The same WHERE for a partial index on both databases the app runs on.

    Spelled as the repositories spell the query (`finished IS false`, not
    `NOT finished`), so that neither planner has to prove one implies the
    other before it will use the index.
    """
    return {"postgresql_where": where, "sqlite_where": where}


class User(Base):
    """User model for storing Telegram user information."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    daily_card_opt_out: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    # The code this user hands out, minted on first ask and stable after.
    referral_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    # Who brought them in. Set once, on the /start that carried a code, and
    # never overwritten: the credit belongs to the first person to invite
    # them, and a second link must not reassign it. A link to another
    # person, so it goes when that person asks to be forgotten.
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # When they came in on an invitation: the marker the discounted payment
    # page reads. Kept apart from `referred_by` because the invitation, and
    # the price it promised, belong to the invitee. Reading `referred_by`
    # instead meant the inviter's /delete_me took the discount away from
    # everyone they had invited.
    referred_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # Relationships
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Who a user invited, for `/invite`'s count and for `erase`. Partial:
        # most people were invited by nobody and need no entry.
        Index(
            "idx_users_referred_by", "referred_by",
            **_partial(column("referred_by").is_not(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_user_id={self.telegram_user_id}, username='{self.username}')>"


class Product(Base):
    """Product model for storing Tribute products."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # ID from Tribute
    type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in cents
    currency: Mapped[str] = mapped_column(String, nullable=False)
    stars_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    t_link: Mapped[str | None] = mapped_column(String, nullable=True)
    web_link: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', amount={self.amount}, currency='{self.currency}')>"


class Payment(Base):
    """Payment model for storing payment transactions."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String, default="tribute", nullable=False)
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )  # Denormalized
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    raw_body: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")
    product: Mapped[Optional["Product"]] = relationship(
        "Product", back_populates="payments"
    )

    __table_args__ = (Index("idx_telegram_user_id_payments", "telegram_user_id"),)

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, event_name='{self.event_name}', amount={self.amount}, user_id={self.user_id})>"


class Subscription(Base):
    """Subscription model for storing user subscriptions."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # ID from Tribute
    period: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)  # NULL = lifetime subscription
    last_event_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "subscription_id", name="uq_user_subscription"),
    )

    @property
    def is_lifetime(self) -> bool:
        """Check if subscription is lifetime (never expires)."""
        return self.expires_at is None

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, subscription_id={self.subscription_id}, status='{self.status}', user_id={self.user_id})>"


class WebhookEvent(Base):
    """WebhookEvent model for logging webhook deliveries."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    body_sha256: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # A hash of what makes two deliveries one event: its name and Tribute's
    # purchase id, or its name, when it happened, the buyer and what was
    # bought (`TributeEvent.idempotency_key`). Tribute stamps each attempt
    # with its own `sent_at`, so a redelivery has a body - and a body hash -
    # of its own. NULL for a delivery with nothing stable to key on.
    event_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("uq_webhook_events_event_key", "event_key", unique=True),)

    def __repr__(self) -> str:
        return f"<WebhookEvent(id={self.id}, name='{self.name}', status_code={self.status_code})>"


class Certificate(Base):
    """Certificate model for storing QR code certificates for free one-time access."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # Unique certificate code
    is_used: Mapped[bool] = mapped_column(default=False, nullable=False)  # Whether certificate was used
    used_by_telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )  # Who used the certificate
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)  # When it was used
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )  # When certificate was created
    # The Tribute purchase that paid for this certificate: a gift's
    # `purchase_id`, which a refund of it carries as well. At most one
    # certificate per purchase. NULL for a printed voucher, and for a gift
    # delivered without an id. It names a purchase, not a person.
    purchase_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when that purchase was refunded or charged back. A revoked
    # certificate cannot be redeemed and no longer grants access to whoever
    # redeemed it already.
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Note: Relationship to User would require a proper foreign key
    # For now, we use telegram_user_id directly without relationship

    __table_args__ = (
        Index("idx_certificate_used_by", "used_by_telegram_user_id"),
        Index("uq_certificates_purchase_id", "purchase_id", unique=True),
    )

    def __repr__(self) -> str:
        status = "revoked" if self.revoked_at else "used" if self.is_used else "available"
        return f"<Certificate(id={self.id}, code='{self.code}', status='{status}')>"


class Room(Base):
    """A shared couple-mode game: two players, one deck, taking turns."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    creator_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String, nullable=True)
    theme: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str] = mapped_column(String, default="questions", nullable=False)
    card_order: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)  # list[int]
    idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=creator, 1=guest
    finished: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # No index on the players or on `updated_at`: a room lives a day and the
    # retention sweep removes it the next, so the table stays a few rows
    # deep, and an index on `updated_at` would make every card turned an
    # update that touches every index.

    def __repr__(self) -> str:
        return f"<Room(code='{self.code}', idx={self.idx}, turn={self.turn})>"


class Steps69Game(Base):
    """«69 ступеней»: one board, one piece, two partners taking turns.

    Follows Room's shape (short code, both players polling, the creator's
    access covering both) with three differences the game needs:

    * `mode` is "duo" or "solo". Solo is one phone passed between partners,
      so there is no guest row and no turn to enforce, but the game still
      lives here: the paywall is enforced server-side, and a game left in
      the middle is what the resume push looks for.
    * Each partner has their own piece, position and roll count. The board
      is walked twice, and the game ends when both pieces stand on 69.
      `used_jokers` is shared, so one game never deals the same task twice.

    No TTL. A pair who stop at cell 45 on a Tuesday are meant to be able to
    come back on Friday and find their piece where they left it, which is
    also what `resume_notified_at` exists to remind them of, once.
    """

    __tablename__ = "steps69_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String, default="duo", nullable=False)
    creator_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # One piece per player, not one per couple. Each partner walks their own
    # board and reads the cell they are standing on, and the game is over
    # only when both have reached 69 — which is the rule the board was
    # written to ("игра не заканчивается, пока оба не достигли пика").
    creator_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    guest_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # The suit each player's piece wears, chosen when the game starts.
    creator_piece: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_piece: Mapped[str | None] = mapped_column(String, nullable=True)
    turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=creator
    # Rolls made by each player. Per player, not per game, because the Joker's
    # tempo rule asks how fast *this* player crossed the board.
    creator_turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guest_turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # The last roll, kept so a partner who polls in mid-animation sees the
    # same move rather than a piece that teleported. One set is enough:
    # only one player moves at a time, and `last_seat` says which.
    last_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_landed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event: Mapped[str | None] = mapped_column(String, nullable=True)

    # A Joker is dealt to the piece standing on it, so each player carries
    # their own; `used_jokers` stays shared, so one game never repeats a task.
    creator_joker_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_joker_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Declared as the list it is. The sibling columns say `Mapped[dict]`
    # with a comment correcting it, which is a type that lies; the column
    # type is given explicitly either way, so the annotation is free to be
    # honest.
    used_jokers: Mapped[list] = mapped_column(JSONEncodedDict, nullable=False)

    finale_choice: Mapped[str | None] = mapped_column(String, nullable=True)
    finished: Mapped[bool] = mapped_column(default=False, nullable=False)
    resume_notified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        # `/mine` asks "creator or guest", and `erase` too: a BitmapOr over
        # these two. The table has no TTL, so without the guest side both
        # scanned every game ever played.
        Index("idx_steps69_creator", "creator_telegram_user_id"),
        Index("idx_steps69_guest", "guest_telegram_user_id"),
        # Games still on the board, by last move: the resume nudge and the
        # retention sweep. Finished games are kept forever and never asked.
        Index(
            "idx_steps69_unfinished_updated", "updated_at",
            **_partial(column("finished").is_(False)),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Steps69Game(code='{self.code}', "
            f"positions={self.creator_position}/{self.guest_position})>"
        )


class Heartbeat(Base):
    """When a process last proved it was alive: one row per process.

    The web process and the bot share nothing but this database, so the bot
    writes its row here every minute (`heartbeat.py`, from its JobQueue) and
    `/health/deep` in the web process reads how old it is. A bot that died,
    or whose event loop is stuck, stops writing - which is the signal.
    """

    __tablename__ = "heartbeats"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    # Naive UTC, like every other timestamp in this schema.
    beat_at: Mapped[datetime] = mapped_column(nullable=False)

    def __repr__(self) -> str:
        return f"<Heartbeat(name='{self.name}', beat_at={self.beat_at})>"


class JobRun(Base):
    """One day's run of a scheduled job: who holds it, and how far it got.

    `jobs.py` claims the row before a job sends or deletes anything - an
    INSERT, or taking over a row whose `lease_until` has passed - and moves
    `cursor` forward after every recipient, so a bot that dies mid-list is
    resumed after the last person it reached and a second bot running at
    the same time finds the row taken. `cursor` is the last key done (a
    Telegram id for the daily card, a game id for the nudge) and is cleared
    when the run finishes. `attempts` counts claims, so a run that keeps
    failing stops being retried. Nothing here is about a person once the run
    is over, and the retention sweep drops rows after `jobs.KEEP`.
    """

    __tablename__ = "job_runs"

    job: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    # Naive UTC, like every other timestamp in this schema.
    lease_until: Mapped[datetime] = mapped_column(nullable=False)
    cursor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # The Sentry Crons check-in this run reports under, kept here so a run
    # taken over after a restart closes the check-in its first owner opened.
    check_in_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<JobRun(job='{self.job}', day={self.day}, finished_at={self.finished_at})>"


class AnalyticsEvent(Base):
    """One thing a person did, counted: a name and one token, never text.

    Written through `vechnost_bot/analytics.py`, which holds the list of
    names and, for each, the closed set its `detail` may come from - a
    paywall's door, a deck, a Library module. `source` is the first-touch
    channel an arrival carries (`src_<tag>`, or ref / invite / gift / push).
    No answers, no card texts, no names, no room codes. Erased with the
    person and dropped after `analytics.KEEP` by the retention sweep.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    # /stats counts by name over a window, and by person for first touch and
    # for coming back; the sweep and /delete_me find rows by age and person.
    __table_args__ = (
        Index("idx_events_name_created", "name", "created_at"),
        Index("idx_events_user_created", "telegram_user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalyticsEvent(id={self.id}, name='{self.name}')>"


class CompatTest(Base):
    """A couples compatibility test: two partners answer 40 questions apart."""

    __tablename__ = "compat_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    creator_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # list[int | None], 40 entries; null means unanswered.
    creator_answers: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)
    guest_answers: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)
    # "<lower id>:<higher id>", set when the guest joins.
    pair_key: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_compat_pair", "pair_key"),
        # `/mine` and `erase` ask "creator or guest"; completed tests have
        # no TTL, so this table only grows.
        Index("idx_compat_creator", "creator_telegram_user_id"),
        Index("idx_compat_guest", "guest_telegram_user_id"),
        # Tests nobody finished, by last answer: the retention sweep.
        Index(
            "idx_compat_unfinished_updated", "updated_at",
            **_partial(column("finished_at").is_(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<CompatTest(code='{self.code}', finished={self.finished_at is not None})>"
