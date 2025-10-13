#!/usr/bin/env python
"""Script to sync products from Tribute API."""

import asyncio
import sys
import logging

from vechnost_bot.payments.services import sync_products_from_tribute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to sync products."""
    try:
        logger.info("Starting product sync from Tribute...")
        count = await sync_products_from_tribute()
        logger.info(f"Successfully synced {count} products!")
        return 0
    except Exception as e:
        logger.error(f"Failed to sync products: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

