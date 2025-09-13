"""Health check endpoint for Railway deployment."""

import asyncio
import logging
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """Simple health check endpoint."""
    return web.json_response({"status": "healthy", "service": "vechnost-bot"})


async def start_health_server(port: int = 8080) -> None:
    """Start a simple health check server."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"Health check server started on port {port}")


def run_health_server() -> None:
    """Run the health server in a separate thread."""
    asyncio.run(start_health_server())
