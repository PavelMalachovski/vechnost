#!/usr/bin/env python
"""Pull the products from the Tribute API into the database.

The same sync `POST /admin/sync-products` runs, for a shell with the
production DATABASE_URL and TRIBUTE_API_KEY in its environment (or `.env`).
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


async def sync() -> int:
    from vechnost_bot.payments.services import sync_products_from_tribute

    try:
        logger.info("Starting product sync from Tribute...")
        count = await sync_products_from_tribute()
        logger.info(f"Successfully synced {count} products!")
        return 0
    except Exception as e:
        logger.error(f"Failed to sync products: {e}", exc_info=True)
        return 1


def main() -> int:
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return asyncio.run(sync())


if __name__ == "__main__":
    sys.exit(main())
