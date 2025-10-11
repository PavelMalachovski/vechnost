"""Storage for user subscriptions and payment data."""

import json
import logging
from datetime import datetime
from typing import Any

from .config import settings
from .payment_models import (
    PaymentStatus,
    PaymentTransaction,
    SubscriptionTier,
    UserSubscription,
)

logger = logging.getLogger(__name__)


class SubscriptionStorage:
    """Storage manager for user subscriptions."""

    def __init__(self):
        """Initialize subscription storage."""
        self._memory_cache: dict[int, UserSubscription] = {}
        self._redis = None

    async def _get_redis(self):
        """Get or create Redis storage instance."""
        if self._redis is None:
            from .hybrid_storage import get_redis_storage
            storage = await get_redis_storage()
            if hasattr(storage, 'redis_storage') and storage.redis_storage:
                self._redis = storage.redis_storage.redis
            else:
                # Fallback to in-memory only
                logger.warning("Redis not available, using memory cache only")
                self._redis = None
        return self._redis

    def _get_subscription_key(self, user_id: int) -> str:
        """Get Redis key for user subscription."""
        return f"subscription:{user_id}"

    def _get_payment_key(self, transaction_id: str) -> str:
        """Get Redis key for payment transaction."""
        return f"payment:{transaction_id}"

    def _get_user_payments_key(self, user_id: int) -> str:
        """Get Redis key for user payments list."""
        return f"user_payments:{user_id}"

    async def get_subscription(self, user_id: int) -> UserSubscription:
        """
        Get user subscription.

        Args:
            user_id: Telegram user ID

        Returns:
            UserSubscription (creates new if not exists)
        """
        # Try memory cache first
        if user_id in self._memory_cache:
            return self._memory_cache[user_id]

        # Try Redis
        key = self._get_subscription_key(user_id)
        redis = await self._get_redis()

        try:
            data = redis.get(key) if redis else None
            if data:
                subscription_dict = json.loads(data)

                # Parse datetime fields
                if subscription_dict.get("subscribed_at"):
                    subscription_dict["subscribed_at"] = datetime.fromisoformat(
                        subscription_dict["subscribed_at"]
                    )
                if subscription_dict.get("expires_at"):
                    subscription_dict["expires_at"] = datetime.fromisoformat(
                        subscription_dict["expires_at"]
                    )
                if subscription_dict.get("last_payment_date"):
                    subscription_dict["last_payment_date"] = datetime.fromisoformat(
                        subscription_dict["last_payment_date"]
                    )
                if subscription_dict.get("last_question_date"):
                    subscription_dict["last_question_date"] = datetime.fromisoformat(
                        subscription_dict["last_question_date"]
                    )

                subscription = UserSubscription(**subscription_dict)
                self._memory_cache[user_id] = subscription
                return subscription
        except Exception as e:
            logger.warning(f"Failed to load subscription from Redis: {e}")

        # Create new subscription
        subscription = UserSubscription(user_id=user_id)
        self._memory_cache[user_id] = subscription

        # Save to Redis
        await self.save_subscription(subscription)

        return subscription

    async def save_subscription(self, subscription: UserSubscription) -> None:
        """
        Save user subscription.

        Args:
            subscription: UserSubscription to save
        """
        # Update memory cache
        self._memory_cache[subscription.user_id] = subscription

        # Save to Redis
        key = self._get_subscription_key(subscription.user_id)
        redis = await self._get_redis()

        try:
            if not redis:
                logger.debug(f"Redis not available, using memory cache only for user {subscription.user_id}")
                return
            # Convert to dict and serialize datetimes
            data = subscription.model_dump()

            if data.get("subscribed_at"):
                data["subscribed_at"] = data["subscribed_at"].isoformat()
            if data.get("expires_at"):
                data["expires_at"] = data["expires_at"].isoformat()
            if data.get("last_payment_date"):
                data["last_payment_date"] = data["last_payment_date"].isoformat()
            if data.get("last_question_date"):
                data["last_question_date"] = data["last_question_date"].isoformat()

            redis.set(
                key,
                json.dumps(data),
                ex=settings.session_ttl * 24  # 24x longer TTL for subscriptions
            )

            logger.debug(f"Saved subscription for user {subscription.user_id}")
        except Exception as e:
            logger.error(f"Failed to save subscription to Redis: {e}")

    async def upgrade_subscription(
        self,
        user_id: int,
        tier: SubscriptionTier,
        duration_days: int = 30,
        payment_id: str | None = None,
    ) -> UserSubscription:
        """
        Upgrade user subscription.

        Args:
            user_id: Telegram user ID
            tier: New subscription tier
            duration_days: Subscription duration
            payment_id: Payment transaction ID

        Returns:
            Updated UserSubscription
        """
        subscription = await self.get_subscription(user_id)

        subscription.tier = tier
        subscription.upgrade_to_premium(duration_days)

        if payment_id:
            subscription.last_payment_id = payment_id
            subscription.last_payment_date = datetime.utcnow()

        await self.save_subscription(subscription)

        logger.info(f"Upgraded user {user_id} to {tier.value}")

        return subscription

    async def renew_subscription(
        self,
        user_id: int,
        duration_days: int = 30,
        payment_id: str | None = None,
    ) -> UserSubscription:
        """
        Renew user subscription.

        Args:
            user_id: Telegram user ID
            duration_days: Renewal duration
            payment_id: Payment transaction ID

        Returns:
            Updated UserSubscription
        """
        subscription = await self.get_subscription(user_id)

        subscription.renew_subscription(duration_days)

        if payment_id:
            subscription.last_payment_id = payment_id
            subscription.last_payment_date = datetime.utcnow()

        await self.save_subscription(subscription)

        logger.info(f"Renewed subscription for user {user_id}")

        return subscription

    async def cancel_subscription(self, user_id: int) -> UserSubscription:
        """
        Cancel user subscription (disable auto-renewal).

        Args:
            user_id: Telegram user ID

        Returns:
            Updated UserSubscription
        """
        subscription = await self.get_subscription(user_id)

        subscription.auto_renew = False
        subscription.tribute_subscription_id = None

        await self.save_subscription(subscription)

        logger.info(f"Cancelled subscription for user {user_id}")

        return subscription

    async def save_payment(self, payment: PaymentTransaction) -> None:
        """
        Save payment transaction.

        Args:
            payment: PaymentTransaction to save
        """
        key = self._get_payment_key(payment.transaction_id)
        redis = await self._get_redis()

        try:
            if not redis:
                logger.debug(f"Redis not available, payment {payment.transaction_id} stored in memory only")
                return
            # Convert to dict and serialize datetimes
            data = payment.model_dump()

            if data.get("created_at"):
                data["created_at"] = data["created_at"].isoformat()
            if data.get("completed_at"):
                data["completed_at"] = data["completed_at"].isoformat()

            redis.set(
                key,
                json.dumps(data),
                ex=settings.session_ttl * 48  # 48x longer TTL for payments
            )

            # Add to user's payments list
            user_payments_key = self._get_user_payments_key(payment.user_id)
            redis.sadd(user_payments_key, payment.transaction_id)

            logger.debug(f"Saved payment {payment.transaction_id}")
        except Exception as e:
            logger.error(f"Failed to save payment to Redis: {e}")

    async def get_payment(self, transaction_id: str) -> PaymentTransaction | None:
        """
        Get payment transaction by ID.

        Args:
            transaction_id: Transaction ID

        Returns:
            PaymentTransaction or None if not found
        """
        key = self._get_payment_key(transaction_id)
        redis = await self._get_redis()

        try:
            data = redis.get(key) if redis else None
            if data:
                payment_dict = json.loads(data)

                # Parse datetime fields
                if payment_dict.get("created_at"):
                    payment_dict["created_at"] = datetime.fromisoformat(
                        payment_dict["created_at"]
                    )
                if payment_dict.get("completed_at"):
                    payment_dict["completed_at"] = datetime.fromisoformat(
                        payment_dict["completed_at"]
                    )

                return PaymentTransaction(**payment_dict)
        except Exception as e:
            logger.warning(f"Failed to load payment from Redis: {e}")

        return None

    async def get_user_payments(self, user_id: int) -> list[PaymentTransaction]:
        """
        Get all payments for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            List of PaymentTransaction
        """
        user_payments_key = self._get_user_payments_key(user_id)
        redis = await self._get_redis()

        try:
            if not redis:
                return []

            transaction_ids = redis.smembers(user_payments_key)

            payments = []
            for transaction_id in transaction_ids:
                if isinstance(transaction_id, bytes):
                    transaction_id = transaction_id.decode("utf-8")

                payment = await self.get_payment(transaction_id)
                if payment:
                    payments.append(payment)

            # Sort by created_at descending
            payments.sort(key=lambda p: p.created_at, reverse=True)

            return payments
        except Exception as e:
            logger.warning(f"Failed to load user payments from Redis: {e}")
            return []

    async def check_and_update_expired_subscriptions(self) -> int:
        """
        Check and update expired subscriptions.

        Returns:
            Number of subscriptions updated
        """
        # This would typically be run as a background task
        # For now, we check on-demand when subscription is accessed
        updated = 0

        for user_id, subscription in list(self._memory_cache.items()):
            if subscription.is_expired() and subscription.tier != SubscriptionTier.FREE:
                subscription.tier = SubscriptionTier.FREE
                await self.save_subscription(subscription)
                updated += 1

        return updated


# Global storage instance
_subscription_storage: SubscriptionStorage | None = None


def get_subscription_storage() -> SubscriptionStorage:
    """Get global subscription storage instance."""
    global _subscription_storage
    if _subscription_storage is None:
        _subscription_storage = SubscriptionStorage()
    return _subscription_storage

