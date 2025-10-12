"""
SQLAlchemy 2.0 models for Tribute webhook data.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, JSON, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class User(Base):
    """User table - stores Telegram user information"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user")


class Product(Base):
    """Product table - stores available products/plans"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'digital', 'subscription'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    stars_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Telegram Stars
    t_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Telegram payment link
    web_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Web payment link
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Payment(Base):
    """Payment table - stores all payment transactions"""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), default="tribute", nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)

    amount: Mapped[Optional[float]] = mapped_column(nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    raw_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")


class Subscription(Base):
    """Subscription table - stores user subscription status"""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subscription_id: Mapped[int] = mapped_column(Integer, nullable=False)

    period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 'monthly', 'yearly'
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")

    # Composite unique constraint
    __table_args__ = (
        Index('ix_user_subscription', 'user_id', 'subscription_id', unique=True),
    )


class WebhookEvent(Base):
    """Webhook events table - audit log of all webhook deliveries"""
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    body_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

