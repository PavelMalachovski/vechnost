"""FastAPI web server for handling Tribute webhooks and the Mini App."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import settings
from ..i18n import Language
from ..logic import localized_game_data
from .database import close_db, init_db
from .services import (
    apply_webhook_event,
    get_products_for_purchase,
    sync_products_from_tribute,
    user_has_access,
)
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent.parent.parent / "webapp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    # Startup
    logger.info("Starting payment webhook server...")
    init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down payment webhook server...")
    await close_db()
    logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title="Vechnost Payment Webhooks",
    description="Payment webhook handler for Tribute integration",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "vechnost-payment-webhooks",
        "payment_enabled": str(settings.enable_payment),
    }


async def _get_purchase_url() -> str:
    """Payment link for the Mini App paywall: first product, else the configured page."""
    for product in await get_products_for_purchase():
        link = product.t_link or product.web_link
        if link:
            return link
    return settings.tribute_payment_url


@app.get("/api/questions")
async def get_questions(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Game content for the Mini App, localized.

    Returns themes with their levels/questions/tasks and an nsfw flag,
    loaded from the same YAML files the bot uses.

    When payments are enabled, the request must carry the Mini App's
    signed initData as ``Authorization: tma <initData>`` and the user
    must have an active payment, subscription or certificate.
    """
    if settings.enable_payment:
        scheme, _, init_data = (authorization or "").partition(" ")
        if scheme.lower() != "tma" or not init_data:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized"},
            )
        try:
            parsed = validate_init_data(init_data, settings.telegram_bot_token)
        except InitDataError as e:
            logger.warning(f"Mini App initData rejected: {e}")
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized"},
            )

        if not await user_has_access(parsed["user"]["id"]):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "payment_required",
                    "payment_url": await _get_purchase_url(),
                },
            )

    try:
        language = Language(lang)
    except ValueError:
        language = Language.RUSSIAN

    game_data = localized_game_data.get_game_data(language)

    themes: dict[str, Any] = {}
    for theme, theme_data in game_data.themes.items():
        entry: dict[str, Any] = {"nsfw": game_data.has_nsfw_content(theme)}
        if "levels" in theme_data:
            entry["levels"] = {
                str(level): {
                    key: value
                    for key, value in level_data.items()
                    if key in ("questions", "tasks")
                }
                for level, level_data in theme_data["levels"].items()
            }
        else:
            for key in ("questions", "tasks"):
                if key in theme_data:
                    entry[key] = theme_data[key]
        themes[theme.value] = entry

    return JSONResponse(
        content={"lang": language.value, "themes": themes},
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/webhooks/tribute")
async def tribute_webhook(request: Request) -> JSONResponse:
    """
    Handle incoming Tribute webhook events.

    This endpoint:
    1. Validates webhook signature
    2. Checks for duplicate webhooks (idempotency)
    3. Processes payment/subscription events
    4. Records webhook in database
    """
    try:
        # Read raw body
        raw_body = await request.body()

        # Log incoming request
        logger.info(f"Received webhook request from {request.client.host if request.client else 'unknown'}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Body length: {len(raw_body)}")

        # Handle empty body (test requests from Tribute)
        if not raw_body or len(raw_body) == 0:
            logger.info("Empty webhook body received (test request?), returning success")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Webhook endpoint is ready",
                },
            )

        # Parse JSON payload
        try:
            payload = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Get headers
        headers = dict(request.headers)

        # Process webhook
        result = await apply_webhook_event(payload, headers, raw_body)

        # Determine status code
        status_code = result.get("code", 200)
        if result["status"] == "error":
            if status_code == 401:
                raise HTTPException(status_code=401, detail=result["message"])
            elif status_code == 400:
                raise HTTPException(status_code=400, detail=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])

        # Return success response
        return JSONResponse(
            status_code=status_code,
            content={
                "status": result["status"],
                "message": result["message"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        )


def verify_admin_token(authorization: str = Header(None)) -> bool:
    """Verify admin token for protected endpoints."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]

    # Verify token against TRIBUTE_API_KEY (simple auth)
    if token != settings.tribute_api_key:
        raise HTTPException(status_code=401, detail="Invalid token")

    return True


@app.post("/admin/sync-products")
async def admin_sync_products(
    authorized: bool = Depends(verify_admin_token),
) -> dict[str, Any]:
    """
    Admin endpoint to manually sync products from Tribute.

    Requires Bearer token authentication using TRIBUTE_API_KEY.
    """
    try:
        count = await sync_products_from_tribute()
        return {
            "status": "success",
            "message": f"Synced {count} products from Tribute",
            "count": count,
        }
    except Exception as e:
        logger.error(f"Error syncing products: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync products: {e}")


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "Vechnost Payment Webhooks",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhooks/tribute",
            "admin_sync": "/admin/sync-products",
            "mini_app": "/app",
            "questions_api": "/api/questions",
        },
    }


# Telegram Mini App (static single-page game)
if WEBAPP_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")
else:
    logger.warning(f"Mini App directory not found: {WEBAPP_DIR}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "vechnost_bot.payments.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

