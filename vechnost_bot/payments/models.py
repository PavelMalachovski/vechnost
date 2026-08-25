"""Database models for payment system."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
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

    __table_args__ = (Index("idx_telegram_user_id", "telegram_user_id"),)

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

    __table_args__ = (
        Index("idx_telegram_user_id_payments", "telegram_user_id"),
        Index("idx_body_sha256", "body_sha256"),
    )

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
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_body_sha256_webhook", "body_sha256"),)

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

    # Note: Relationship to User would require a proper foreign key
    # For now, we use telegram_user_id directly without relationship

    __table_args__ = (
        Index("idx_certificate_code", "code"),
        Index("idx_certificate_used_by", "used_by_telegram_user_id"),
    )

    @property
    def is_valid(self) -> bool:
        """Check if certificate is valid (not used)."""
        return not self.is_used

    def __repr__(self) -> str:
        status = "used" if self.is_used else "available"
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

    __table_args__ = (Index("idx_room_code", "code"),)

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
    * `turns` counts rolls, and feeds the Joker's tempo rule. `used_jokers`
      keeps a pair from drawing the same task twice in one game.
    * `reactions` is a short tail of emoji, each with a monotonic `seq`, so
      a polling client can tell what it has not animated yet without a
      second column to hold the counter.

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

    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=creator
    turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # The last roll, kept so a partner who polls in mid-animation sees the
    # same move rather than a piece that teleported.
    last_roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_landed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event: Mapped[str | None] = mapped_column(String, nullable=True)

    joker_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Declared as the lists they are. The sibling columns say `Mapped[dict]`
    # with a comment correcting it, which is a type that lies; the column
    # type is given explicitly either way, so the annotation is free to be
    # honest.
    used_jokers: Mapped[list] = mapped_column(JSONEncodedDict, nullable=False)
    reactions: Mapped[list] = mapped_column(JSONEncodedDict, nullable=False)

    finale_choice: Mapped[str | None] = mapped_column(String, nullable=True)
    finished: Mapped[bool] = mapped_column(default=False, nullable=False)
    resume_notified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_steps69_code", "code"),
        Index("idx_steps69_creator", "creator_telegram_user_id"),
    )

    def __repr__(self) -> str:
        return f"<Steps69Game(code='{self.code}', position={self.position})>"


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
        Index("idx_compat_code", "code"),
        Index("idx_compat_pair", "pair_key"),
    )

    def __repr__(self) -> str:
        return f"<CompatTest(code='{self.code}', finished={self.finished_at is not None})>"
