"""Database models for payment system."""

import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    Text,
    Index,
    UniqueConstraint,
    ForeignKey,
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
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # Relationships
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
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
    stars_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    t_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    web_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    payments: Mapped[List["Payment"]] = relationship(
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
    product_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
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
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # NULL = lifetime subscription
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
    processed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_body_sha256_webhook", "body_sha256"),)

    def __repr__(self) -> str:
        return f"<WebhookEvent(id={self.id}, name='{self.name}', status_code={self.status_code})>"


class Certificate(Base):
    """Certificate model for storing QR code certificates for free one-time access."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # Unique certificate code
    is_used: Mapped[bool] = mapped_column(default=False, nullable=False)  # Whether certificate was used
    used_by_telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )  # Who used the certificate
    used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # When it was used
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
