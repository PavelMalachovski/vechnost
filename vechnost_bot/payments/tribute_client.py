"""Tribute API client for interacting with Tribute payment service."""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class TributeProduct:
    """Tribute product data model."""

    id: int
    type: str
    name: str
    amount: int  # in cents
    currency: str
    stars_amount: Optional[int] = None
    t_link: Optional[str] = None
    web_link: Optional[str] = None


class TributeAPIError(Exception):
    """Exception raised for Tribute API errors."""

    pass


class TributeClient:
    """Client for interacting with Tribute API."""

    def __init__(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ):
        """Initialize Tribute client."""
        self.api_key = api_key or settings.tribute_api_key
        self.base_url = base_url or settings.tribute_base_url

        if not self.api_key:
            logger.warning("Tribute API key not configured")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def list_products(self) -> List[TributeProduct]:
        """
        Fetch list of products from Tribute API.

        Returns:
            List of TributeProduct objects
        """
        if not self.api_key:
            raise TributeAPIError("Tribute API key not configured")

        url = f"{self.base_url}/v1/products"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

                data = response.json()
                products = []

                # Parse products from response
                # Note: Adjust this based on actual Tribute API response structure
                products_data = data.get("products", []) if isinstance(data, dict) else data

                for item in products_data:
                    product = TributeProduct(
                        id=item.get("id"),
                        type=item.get("type", ""),
                        name=item.get("name", ""),
                        amount=item.get("amount", 0),
                        currency=item.get("currency", "USD"),
                        stars_amount=item.get("stars_amount"),
                        t_link=item.get("t_link"),
                        web_link=item.get("web_link"),
                    )
                    products.append(product)

                logger.info(f"Fetched {len(products)} products from Tribute")
                return products

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching products: {e.response.status_code} - {e.response.text}")
            raise TributeAPIError(
                f"Failed to fetch products: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error(f"Request error fetching products: {e}")
            raise TributeAPIError("Failed to fetch products: network error") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching products: {e}")
            raise TributeAPIError(f"Failed to fetch products: {e}") from e

    async def get_subscription_status(
        self, user_ref: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get subscription status for a user.

        Args:
            user_ref: User reference ID (e.g., telegram_user_id)

        Returns:
            Subscription data or None if not found
        """
        if not self.api_key:
            raise TributeAPIError("Tribute API key not configured")

        url = f"{self.base_url}/v1/subscriptions/{user_ref}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(
                f"HTTP error fetching subscription: {e.response.status_code} - {e.response.text}"
            )
            raise TributeAPIError(
                f"Failed to fetch subscription: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error(f"Request error fetching subscription: {e}")
            raise TributeAPIError(
                "Failed to fetch subscription: network error"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error fetching subscription: {e}")
            raise TributeAPIError(f"Failed to fetch subscription: {e}") from e

