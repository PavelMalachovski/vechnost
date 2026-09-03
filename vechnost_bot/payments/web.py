"""FastAPI web server for handling Tribute webhooks and the Mini App."""

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import referrals
from ..config import settings
from ..freemium import FREE_CARDS_PER_DECK, free_slice, is_index_free
from ..i18n import Language, get_text
from ..logic import localized_game_data
from ..models import ContentType, Theme
from ..renderer import get_background_path, render_card_bytes
from .compat_api import router as compat_router
from .database import close_db, get_db, init_db
from .library_api import router as library_router
from .repositories import UserRepository
from .rooms import router as rooms_router
from .services import (
    apply_webhook_event,
    get_price_label,
    get_products_for_purchase,
    sync_products_from_tribute,
    user_has_access,
)
from .steps69_api import router as steps69_router
from .throttle import throttle
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent.parent.parent / "webapp"
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"


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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers the app had none of.

    The Mini App runs inside Telegram's own webview, which frames it itself,
    so `X-Frame-Options: DENY` would break the product. `SAMEORIGIN` refuses
    everyone else, which is the part that matters: nothing here should be
    embedded in a stranger's page and clicked through.

    `nosniff` stops a browser second-guessing a content type, and the
    referrer policy keeps a room code out of the Referer header on any link
    a user follows out of the app.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# The API authenticates with an `Authorization` header, never a cookie, so a
# cross-site request cannot ride along on a session the browser holds and
# there is no CSRF to block. What CORS still decides is who may *read* a
# response from script: without it a page anywhere could fetch the deck, the
# board or the compatibility questions and use them as its own. The Mini App
# is same-origin with this server and needs no allowance at all, so the
# allowlist is empty unless a deployment sets one.
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in (settings.cors_allow_origins or "").split(",")
    if origin.strip()
]
if _ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Guest-Id"],
    )
    logger.info(f"CORS enabled for {_ALLOWED_ORIGINS}")

# Refuse a request that arrived claiming a hostname this deployment does not
# answer to. Left open by default because the platform hostname is not known
# here; set ALLOWED_HOSTS in production and a host-header forgery stops being
# able to poison a link the bot builds.
_ALLOWED_HOSTS = [
    host.strip()
    for host in (settings.allowed_hosts or "").split(",")
    if host.strip()
]
if _ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)
    logger.info(f"Host header restricted to {_ALLOWED_HOSTS}")


app.include_router(rooms_router)
app.include_router(library_router)
app.include_router(compat_router)
app.include_router(steps69_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "vechnost-payment-webhooks",
        "payment_enabled": str(settings.enable_payment),
    }


async def _get_purchase_url(referred: bool = False) -> str:
    """Payment link for the Mini App paywall.

    A user who arrived on someone's referral link is sent to the discounted
    Tribute product instead. Tribute owns the price, so choosing the page is
    the whole of the discount; with no discounted page configured everyone
    gets the ordinary one and the referral is still recorded.
    """
    discounted = referrals.payment_url_for(referred)
    if discounted:
        return discounted
    for product in await get_products_for_purchase():
        link = product.t_link or product.web_link
        if link:
            return link
    return settings.tribute_payment_url


async def _caller_is_referred(authorization: str | None) -> bool:
    """Whether this Mini App caller came in on someone's invite."""
    if not settings.enable_payment:
        return False
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return False
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
    except InitDataError:
        return False
    try:
        async with get_db() as session:
            return await UserRepository.is_referred(session, parsed["user"]["id"])
    except Exception as e:
        logger.warning(f"Referral lookup failed: {e}")
        return False


async def _request_is_paid(authorization: str | None) -> bool:
    """
    Whether this Mini App request belongs to a paying user.

    With payments disabled everyone is "paid". Otherwise the request must
    carry valid signed initData (``Authorization: tma <initData>``) and the
    user must have an active payment, subscription or certificate; anything
    else — including a missing or forged header — is just an unpaid visitor.
    """
    if not settings.enable_payment:
        return True

    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return False
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
    except InitDataError as e:
        logger.warning(f"Mini App initData rejected: {e}")
        return False
    return await user_has_access(parsed["user"]["id"])


def _deck_payload(deck: dict[str, Any], paid: bool) -> dict[str, Any]:
    """Questions/tasks of one deck; unpaid users get the free prefix + totals."""
    payload: dict[str, Any] = {}
    for key in ("questions", "tasks"):
        if key in deck:
            items = deck[key]
            payload[key] = items if paid else free_slice(items)
            payload[f"{key}_total"] = len(items)
    return payload


@app.get("/api/questions")
async def get_questions(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Game content for the Mini App, localized.

    Returns themes with their levels/questions/tasks and an nsfw flag,
    loaded from the same YAML files the bot uses.

    Freemium: unpaid users get only the first FREE_CARDS_PER_DECK cards
    of every deck, plus an ``access`` block with the purchase link and
    price for the paywall.
    """
    paid = await _request_is_paid(authorization)

    language = Language.coerce(lang)

    game_data = localized_game_data.get_game_data(language)

    themes: dict[str, Any] = {}
    for theme, theme_data in game_data.themes.items():
        entry: dict[str, Any] = {"nsfw": game_data.has_nsfw_content(theme)}
        if "levels" in theme_data:
            entry["levels"] = {
                str(level): _deck_payload(level_data, paid)
                for level, level_data in theme_data["levels"].items()
            }
        else:
            entry.update(_deck_payload(theme_data, paid))
        themes[theme.value] = entry

    access: dict[str, Any] = {"paid": paid}
    if not paid:
        referred = await _caller_is_referred(authorization)
        access["free_per_deck"] = FREE_CARDS_PER_DECK
        access["payment_url"] = await _get_purchase_url(referred)
        access["price"] = await get_price_label()
        if referred and referrals.discount_available():
            access["discount_percent"] = settings.referral_discount_percent

    bot_url = f"https://t.me/{settings.bot_username}" if settings.bot_username else None

    return JSONResponse(
        content={
            "lang": language.value,
            "themes": themes,
            "access": access,
            "bot_url": bot_url,
        },
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/card", dependencies=[Depends(throttle("render"))])
async def get_card_image(
    theme: str,
    idx: int,
    level: int = 0,
    type: str = "questions",
    lang: str = "ru",
    authorization: str | None = Header(default=None),
) -> Response:
    """
    One card rendered as a branded share image (JPEG).

    Free-preview cards are public; cards past the free prefix require the
    same paid initData as the full question list.
    """
    try:
        theme_enum = Theme(theme)
        content_type = ContentType(type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="unknown deck") from e

    language = Language.coerce(lang)

    items = localized_game_data.get_content(
        theme_enum, level or None, content_type, language
    )
    if not items or idx < 0 or idx >= len(items):
        raise HTTPException(status_code=404, detail="card not found")

    if not is_index_free(idx) and not await _request_is_paid(authorization):
        raise HTTPException(status_code=403, detail="payment_required")

    bg_path = get_background_path(
        theme_enum.value_short(),
        level,
        "q" if content_type == ContentType.QUESTIONS else "t",
    )
    theme_label = get_text(f"themes.{theme_enum.value}", language)
    plain_label = "".join(
        ch for ch in theme_label if ch.isalpha() or ch.isspace()
    ).strip()
    footer = f"{plain_label} · {idx + 1}/{len(items)}"
    watermark = (
        f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    )

    # Off the loop, and memoised per card: a composite is ~25 ms of Pillow,
    # and running it inline here stalled the webhook and every game.
    image = await asyncio.to_thread(
        render_card_bytes, items[idx], bg_path, footer, watermark
    )
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# A Tribute event is a few hundred bytes. Anything past this is not one, and
# reading it would only be work done for a stranger before the signature is
# looked at.
MAX_WEBHOOK_BODY = 64 * 1024


@app.post("/webhooks/tribute", dependencies=[Depends(throttle("webhook"))])
async def tribute_webhook(request: Request) -> JSONResponse:
    """
    Handle incoming Tribute webhook events.

    The service verifies the signature before it touches the database and
    records only deliveries it actually processed, so a rejected one can be
    retried; see `services.apply_webhook_event`. This layer bounds the body,
    parses it, and translates the result into a status code.
    """
    try:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_WEBHOOK_BODY:
            raise HTTPException(status_code=413, detail="payload too large")

        raw_body = await request.body()
        if len(raw_body) > MAX_WEBHOOK_BODY:
            raise HTTPException(status_code=413, detail="payload too large")

        # The address only: the headers carry the signature, and a body can
        # carry a buyer's name, so neither goes to the log.
        logger.info(
            f"Received webhook request from "
            f"{request.client.host if request.client else 'unknown'} "
            f"({len(raw_body)} bytes)"
        )

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
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

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

        # What was done, in the reply Tribute's delivery log keeps: an
        # operator reading "ignore" there learns more than "success".
        content = {"status": result["status"], "message": result["message"]}
        if "action" in result:
            content["action"] = result["action"]
        return JSONResponse(status_code=status_code, content=content)

    except HTTPException:
        raise
    except Exception as e:
        # The detail goes to whoever sent the request, and an unhandled
        # exception here carries SQL, driver and path fragments. Log it in
        # full, tell the caller only that it failed.
        logger.error(f"Unexpected error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal error") from e


def verify_admin_token(authorization: str = Header(None)) -> bool:
    """Verify the bearer token guarding the /admin endpoints.

    Compared with `compare_digest`, not `!=`: a plain comparison returns as
    soon as two bytes differ, which leaks the length of the shared prefix and
    turns guessing the token into guessing one character at a time.
    """
    secret = settings.admin_secret
    if not secret:
        # No secret configured means no way to authenticate, which must read
        # as "closed", not as "everyone is an admin".
        logger.error("Neither ADMIN_TOKEN nor TRIBUTE_API_KEY is set: /admin is closed")
        raise HTTPException(status_code=503, detail="admin endpoints are not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Invalid token")

    return True


@app.post("/admin/sync-products", dependencies=[Depends(throttle("admin"))])
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
        raise HTTPException(status_code=500, detail="failed to sync products") from e


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

# The Mini App renders on the same card art the bot composites onto, so
# it needs the PNGs themselves. Read-only and public: these are the same
# images every user already receives as photos.
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
else:
    logger.warning(f"Assets directory not found: {ASSETS_DIR}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "vechnost_bot.payments.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

