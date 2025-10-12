"""
Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class WebhookResponse(BaseModel):
    """Standard webhook response"""
    ok: bool = True
    dup: Optional[bool] = None


class UserBase(BaseModel):
    """Base user schema"""
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user"""
    pass


class User(UserBase):
    """Complete user schema"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentBase(BaseModel):
    """Base payment schema"""
    event_name: str
    telegram_user_id: int
    amount: Optional[float] = None
    currency: str = "RUB"


class Payment(PaymentBase):
    """Complete payment schema"""
    id: int
    provider: str
    user_id: int
    product_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    """Base subscription schema"""
    subscription_id: int
    period: Optional[str] = None
    status: str = "active"
    expires_at: Optional[datetime] = None


class Subscription(SubscriptionBase):
    """Complete subscription schema"""
    id: int
    user_id: int
    last_event_at: datetime

    class Config:
        from_attributes = True

