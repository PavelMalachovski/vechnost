"""Payment and subscription models for Vechnost bot."""

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    """Available subscription tiers."""

    FREE = "free"
    PREMIUM = "premium"
    VIP = "vip"  # Future expansion


class PaymentStatus(str, Enum):
    """Payment status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class SubscriptionFeatures(BaseModel):
    """Features available for each subscription tier."""

    # Content access
    basic_themes: bool = True  # Acquaintance, For Couples
    premium_themes: bool = False  # Sex, Provocation

    # Limits
    daily_question_limit: int | None = None  # None = unlimited

    # Additional features
    priority_support: bool = False
    custom_backgrounds: bool = False

    # Future features
    private_sessions: bool = False
    exclusive_content: bool = False


class SubscriptionPlan(BaseModel):
    """Subscription plan definition."""

    tier: SubscriptionTier
    name: str
    description: str
    price_monthly: float  # in RUB
    price_yearly: float | None = None
    features: SubscriptionFeatures
    tribute_product_id: str | None = None  # Tribute product ID


class UserSubscription(BaseModel):
    """User subscription state."""

    user_id: int
    tier: SubscriptionTier = SubscriptionTier.FREE

    # Subscription period
    subscribed_at: datetime | None = None
    expires_at: datetime | None = None

    # Payment tracking
    last_payment_id: str | None = None
    last_payment_date: datetime | None = None

    # Auto-renewal
    auto_renew: bool = False
    tribute_subscription_id: str | None = None

    # Usage tracking
    questions_today: int = 0
    last_question_date: datetime | None = None

    def is_active(self) -> bool:
        """Check if subscription is active."""
        if self.tier == SubscriptionTier.FREE:
            return True

        if self.expires_at is None:
            return False

        return datetime.utcnow() < self.expires_at

    def is_expired(self) -> bool:
        """Check if subscription is expired."""
        return not self.is_active()

    def days_remaining(self) -> int:
        """Get days remaining in subscription."""
        if not self.is_active() or self.expires_at is None:
            return 0

        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    def can_access_premium_themes(self) -> bool:
        """Check if user can access premium themes."""
        return self.tier in [SubscriptionTier.PREMIUM, SubscriptionTier.VIP] and self.is_active()

    def can_ask_question_today(self) -> bool:
        """Check if user can ask a question today (rate limiting for free tier)."""
        if self.tier != SubscriptionTier.FREE:
            return True  # No limits for paid tiers

        # Reset daily counter if it's a new day
        if self.last_question_date is None or \
           self.last_question_date.date() < datetime.utcnow().date():
            return True

        # Free tier: 10 questions per day
        return self.questions_today < 10

    def increment_question_count(self) -> None:
        """Increment daily question count."""
        today = datetime.utcnow().date()

        if self.last_question_date is None or self.last_question_date.date() < today:
            self.questions_today = 1
        else:
            self.questions_today += 1

        self.last_question_date = datetime.utcnow()

    def upgrade_to_premium(self, duration_days: int = 30) -> None:
        """Upgrade user to premium tier."""
        self.tier = SubscriptionTier.PREMIUM
        self.subscribed_at = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(days=duration_days)

    def renew_subscription(self, duration_days: int = 30) -> None:
        """Renew subscription."""
        if self.expires_at and self.expires_at > datetime.utcnow():
            # Extend from current expiry date
            self.expires_at = self.expires_at + timedelta(days=duration_days)
        else:
            # Start new subscription
            self.subscribed_at = datetime.utcnow()
            self.expires_at = datetime.utcnow() + timedelta(days=duration_days)


class PaymentTransaction(BaseModel):
    """Payment transaction record."""

    transaction_id: str
    user_id: int

    # Payment details
    amount: float
    currency: str = "RUB"

    # Tribute details
    tribute_payment_id: str | None = None
    tribute_customer_id: str | None = None

    # Status
    status: PaymentStatus = PaymentStatus.PENDING

    # Subscription details
    subscription_tier: SubscriptionTier
    duration_days: int = 30

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Metadata
    metadata: dict = Field(default_factory=dict)

    def mark_completed(self) -> None:
        """Mark payment as completed."""
        self.status = PaymentStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def mark_failed(self) -> None:
        """Mark payment as failed."""
        self.status = PaymentStatus.FAILED


# Predefined subscription plans
SUBSCRIPTION_PLANS = {
    SubscriptionTier.FREE: SubscriptionPlan(
        tier=SubscriptionTier.FREE,
        name="Базовый",
        description="🆓 Бесплатный доступ: 10 вопросов в день",
        price_monthly=0.0,
        features=SubscriptionFeatures(
            basic_themes=True,
            premium_themes=False,
            daily_question_limit=10,
            priority_support=False,
        )
    ),
    SubscriptionTier.PREMIUM: SubscriptionPlan(
        tier=SubscriptionTier.PREMIUM,
        name="Премиум",
        description="⭐ Безлимитный доступ ко всем темам",
        price_monthly=299.0,
        price_yearly=2990.0,
        features=SubscriptionFeatures(
            basic_themes=True,
            premium_themes=True,
            daily_question_limit=None,  # Unlimited
            priority_support=True,
            custom_backgrounds=True,
        ),
        tribute_product_id="vechnost_premium_monthly"  # Configure in Tribute
    ),
}


def get_subscription_plan(tier: SubscriptionTier) -> SubscriptionPlan:
    """Get subscription plan by tier."""
    return SUBSCRIPTION_PLANS[tier]

