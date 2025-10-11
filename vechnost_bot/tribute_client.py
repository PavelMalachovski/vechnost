"""Tribute payment system API client."""

import hashlib
import hmac
import json
import logging
from typing import Any

import aiohttp
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)


class TributePaymentLink(BaseModel):
    """Tribute payment link response."""

    payment_url: str
    payment_id: str
    expires_at: str | None = None


class TributeCustomer(BaseModel):
    """Tribute customer information."""

    customer_id: str
    email: str | None = None
    telegram_id: int | None = None


class TributePaymentStatus(BaseModel):
    """Tribute payment status response."""

    payment_id: str
    status: str  # pending, completed, failed, refunded
    amount: float
    currency: str
    customer_id: str | None = None
    metadata: dict = {}


class TributeWebhookEvent(BaseModel):
    """Tribute webhook event."""

    event_type: str  # payment.completed, payment.failed, subscription.renewed, etc.
    payment_id: str
    customer_id: str | None = None
    amount: float
    currency: str
    status: str
    metadata: dict = {}
    timestamp: str


class TributeClient:
    """Client for interacting with Tribute payment API."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize Tribute client."""
        self.api_key = api_key or settings.tribute_api_key
        self.api_secret = api_secret or settings.tribute_api_secret
        self.base_url = base_url or settings.tribute_base_url

        if not self.api_key:
            logger.warning("Tribute API key not configured")

        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self.session

    async def close(self) -> None:
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def create_payment_link(
        self,
        amount: float,
        currency: str = "RUB",
        description: str = "",
        user_id: int | None = None,
        metadata: dict | None = None,
        return_url: str | None = None,
    ) -> TributePaymentLink:
        """
        Create a payment link for user.

        Args:
            amount: Payment amount
            currency: Currency code (RUB, USD, etc.)
            description: Payment description
            user_id: Telegram user ID
            metadata: Additional metadata to store with payment
            return_url: URL to redirect after payment

        Returns:
            TributePaymentLink with payment URL
        """
        if not self.api_key:
            raise ValueError("Tribute API key not configured")

        session = await self._get_session()

        payload = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "metadata": metadata or {},
        }

        if user_id:
            payload["customer"] = {"telegram_id": user_id}

        if return_url:
            payload["return_url"] = return_url

        try:
            async with session.post(
                f"{self.base_url}/v1/payments",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

                logger.info(f"Created payment link: {data.get('payment_id')}")

                return TributePaymentLink(
                    payment_url=data["payment_url"],
                    payment_id=data["payment_id"],
                    expires_at=data.get("expires_at"),
                )
        except aiohttp.ClientError as e:
            logger.error(f"Failed to create payment link: {e}")
            raise

    async def get_payment_status(self, payment_id: str) -> TributePaymentStatus:
        """
        Get payment status by ID.

        Args:
            payment_id: Tribute payment ID

        Returns:
            TributePaymentStatus
        """
        if not self.api_key:
            raise ValueError("Tribute API key not configured")

        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/v1/payments/{payment_id}"
            ) as response:
                response.raise_for_status()
                data = await response.json()

                return TributePaymentStatus(
                    payment_id=data["payment_id"],
                    status=data["status"],
                    amount=data["amount"],
                    currency=data["currency"],
                    customer_id=data.get("customer_id"),
                    metadata=data.get("metadata", {}),
                )
        except aiohttp.ClientError as e:
            logger.error(f"Failed to get payment status: {e}")
            raise

    async def create_subscription(
        self,
        amount: float,
        interval: str = "month",  # month, year
        user_id: int | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """
        Create a recurring subscription.

        Args:
            amount: Subscription amount
            interval: Billing interval (month, year)
            user_id: Telegram user ID
            metadata: Additional metadata

        Returns:
            Subscription data with payment URL
        """
        if not self.api_key:
            raise ValueError("Tribute API key not configured")

        session = await self._get_session()

        payload = {
            "amount": amount,
            "interval": interval,
            "metadata": metadata or {},
        }

        if user_id:
            payload["customer"] = {"telegram_id": user_id}

        try:
            async with session.post(
                f"{self.base_url}/v1/subscriptions",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

                logger.info(f"Created subscription: {data.get('subscription_id')}")
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Failed to create subscription: {e}")
            raise

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """
        Cancel a subscription.

        Args:
            subscription_id: Tribute subscription ID

        Returns:
            True if cancelled successfully
        """
        if not self.api_key:
            raise ValueError("Tribute API key not configured")

        session = await self._get_session()

        try:
            async with session.post(
                f"{self.base_url}/v1/subscriptions/{subscription_id}/cancel"
            ) as response:
                response.raise_for_status()
                logger.info(f"Cancelled subscription: {subscription_id}")
                return True
        except aiohttp.ClientError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False

    def verify_webhook_signature(
        self,
        payload: str | bytes,
        signature: str,
    ) -> bool:
        """
        Verify Tribute webhook signature.

        Args:
            payload: Raw webhook payload
            signature: Signature from X-Tribute-Signature header

        Returns:
            True if signature is valid
        """
        if not settings.tribute_webhook_secret:
            logger.warning("Tribute webhook secret not configured")
            return False

        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        expected_signature = hmac.new(
            settings.tribute_webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    async def process_webhook_event(
        self,
        payload: dict[str, Any]
    ) -> TributeWebhookEvent:
        """
        Process webhook event from Tribute.

        Args:
            payload: Webhook payload

        Returns:
            TributeWebhookEvent
        """
        return TributeWebhookEvent(
            event_type=payload.get("event_type", "unknown"),
            payment_id=payload.get("payment_id", ""),
            customer_id=payload.get("customer_id"),
            amount=payload.get("amount", 0.0),
            currency=payload.get("currency", "RUB"),
            status=payload.get("status", "unknown"),
            metadata=payload.get("metadata", {}),
            timestamp=payload.get("timestamp", ""),
        )


# Global client instance
_tribute_client: TributeClient | None = None


def get_tribute_client() -> TributeClient:
    """Get global Tribute client instance."""
    global _tribute_client
    if _tribute_client is None:
        _tribute_client = TributeClient()
    return _tribute_client


async def cleanup_tribute_client() -> None:
    """Cleanup Tribute client."""
    global _tribute_client
    if _tribute_client:
        await _tribute_client.close()
        _tribute_client = None

