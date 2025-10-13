"""FastAPI web server for handling Tribute webhooks."""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse

from ..config import settings
from .database import init_db, close_db
from .services import apply_webhook_event, sync_products_from_tribute

logger = logging.getLogger(__name__)


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
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "vechnost-payment-webhooks",
        "payment_enabled": str(settings.enable_payment),
    }


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
) -> Dict[str, Any]:
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
async def root() -> Dict[str, str]:
    """Root endpoint."""
    return {
        "service": "Vechnost Payment Webhooks",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhooks/tribute",
            "admin_sync": "/admin/sync-products",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "vechnost_bot.payments.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

