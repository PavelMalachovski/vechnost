"""FastAPI web server for handling Tribute webhooks and the Mini App."""

import asyncio
import hmac
import json
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.types import Scope

from .. import analytics, referrals
from ..config import settings
from ..freemium import FREE_CARDS_PER_DECK, free_slice, is_index_free
from ..heartbeat import deep_status
from ..i18n import Language, get_text
from ..logic import localized_game_data
from ..models import ContentType, Theme
from ..renderer import get_background_path, render_card_bytes
from .compat_api import router as compat_router
from .database import close_db, get_db, init_db
from .grant_notify import notify_access_granted
from .library_api import router as library_router
from .repositories import UserRepository
from .rooms import room_dealt_card
from .rooms import router as rooms_router
from .services import (
    apply_webhook_event,
    get_price_label,
    purchase_url_for,
    sync_products_from_tribute,
    user_has_access,
    user_is_referred,
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
    # Startup. Logging and Sentry first: this is the process that takes the
    # payments, and it never set either up - its INFO lines were dropped,
    # its warnings printed without level or time, and an exception here
    # never reached Sentry. Monitoring failing must not stop the server.
    try:
        from ..monitoring import initialize_monitoring

        initialize_monitoring()
    except Exception as e:
        logger.warning(f"Monitoring could not be initialised: {e}")
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


# Who may put the app in a frame: ourselves, and Telegram. The phone and
# desktop clients open a Mini App in a native webview, but Telegram Web
# (web.telegram.org, the K and A clients) opens it in an <iframe> whose
# parent is Telegram's origin, not ours.
FRAME_ANCESTORS = "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """A 422 that says what failed and where, without echoing the input.

    FastAPI's default repeats each error's `input`, and a body such as
    `{"index": 1e309}` parses to infinity, which the JSON encoder refuses to
    write: the 422 itself became a 500. The input is the caller's own
    request, so nothing is lost by not sending it back.
    """
    errors = [
        {
            "loc": [part if isinstance(part, int) else str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


# Compression. The Mini App is one 211 KB page of text and /api/questions
# another 54 KB, and both went out as they were: about 60 KB in gzip, on
# the first screen of a phone that may be on a train. Starlette leaves
# images, fonts and anything already encoded alone.
#
# Added before the headers middleware below, which makes it the inner of
# the two: that one hands every response on as a stream, and GZip treats a
# stream as large whatever its size, so outside it a 30-byte /health came
# back gzipped. Inside, it sees the app's response whole, and a response
# under a kilobyte goes out as it is. Level 6, not Starlette's 9: on the
# page, 9 took twice the CPU of 6 to save 222 bytes of 63 KB.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers the app had none of.

    Framing is allowed to Telegram and refused to everyone else, which is
    the part that matters: nothing here should be embedded in a stranger's
    page and clicked through. It used to be `X-Frame-Options: SAMEORIGIN`,
    on the belief that Telegram frames the app the same way everywhere; in
    Telegram Web the parent is web.telegram.org, SAMEORIGIN refused it, and
    the Mini App opened blank there (Chromium: "Refused to display ... in a
    frame"). CSP `frame-ancestors` can name Telegram, and every browser that
    runs Telegram Web honours it.

    `nosniff` stops a browser second-guessing a content type, and the
    referrer policy keeps a room code out of the Referer header on any link
    a user follows out of the app.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Content-Security-Policy", FRAME_ANCESTORS)
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


class CachedStaticFiles(StaticFiles):
    """StaticFiles that tells the browser how long it may keep each file.

    Without it every launch asked again for the fonts and the card art -
    an ETag each, so a 304 at best, but twenty round trips before the home
    screen could draw its fan of decks. `cache_control` maps the file being
    served to the header it goes out with, a 304 included: a revalidation
    that did not say so would leave the cached copy stale again at once.
    """

    def __init__(self, *, cache_control: Callable[[Path], str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cache_control = cache_control

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = self._cache_control(Path(full_path))
        return response


# The page itself is always revalidated: a deploy has to reach the next
# launch, and a 304 costs one round trip. The fonts are the same bytes for
# months, so a month. The card art can be regenerated
# (scripts/generate_card_assets.py), so a day, then served from the cache
# while the browser checks in the background.
PAGE_CACHE = "no-cache"
FONT_CACHE = "public, max-age=2592000"
ASSET_CACHE = "public, max-age=86400, stale-while-revalidate=604800"


def _webapp_cache_control(path: Path) -> str:
    return FONT_CACHE if path.parent.name == "fonts" else PAGE_CACHE


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
async def health_check() -> dict[str, str | None]:
    """Health check endpoint, and which commit is answering.

    Railway sets RAILWAY_GIT_COMMIT_SHA on a deploy from GitHub; reporting
    it lets the post-deploy smoke test (scripts/smoke_production.py) wait
    for the commit it was started for instead of testing the old one.
    """
    return {
        "status": "ok",
        "service": "vechnost-payment-webhooks",
        "payment_enabled": str(settings.enable_payment),
        "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA") or None,
    }


@app.get("/health/deep")
async def deep_health_check() -> JSONResponse:
    """Whether the database answers and the bot is alive: 200, or 503.

    Not Railway's healthcheck - that is `/health`, which must stay light so
    a database blip or a restarting bot never blocks a deploy or recycles a
    web process that serves fine. This one is for the smoke test and for
    whoever is looking: `SELECT 1`, and the age of the heartbeat the bot
    writes every minute (`heartbeat.py`), which stops when the bot dies or
    its event loop is stuck.
    """
    healthy, checks = await deep_status()
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "unhealthy",
            "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA") or None,
            "checks": checks,
        },
        headers={"Cache-Control": "no-store"},
    )


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
    return await user_is_referred(parsed["user"]["id"])


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


class ClientEvent(BaseModel):
    """One thing the Mini App saw a person do: a name from
    `analytics.CLIENT_EVENTS`, one allow-listed token, and for an arrival
    the channel it came by. Anything else in them is dropped, not stored."""

    name: str = Field(max_length=32)
    detail: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=40)


def _telegram_id(authorization: str | None) -> int | None:
    """The person a Mini App request is signed for, or None.

    Checked whether or not payments are on: a count is only worth keeping
    for somebody Telegram vouches for.
    """
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return None
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
        return int(parsed["user"]["id"])
    except (InitDataError, KeyError, TypeError, ValueError):
        return None


@app.post("/api/events", status_code=204, dependencies=[Depends(throttle("events"))])
async def client_event(
    body: ClientEvent, authorization: str | None = Header(default=None)
) -> Response:
    """Count one thing the Mini App saw: an arrival, an opened deck or
    module, a shared invite, a paywall and a tap on its button.

    Only what the client can honestly know is taken from it
    (`analytics.CLIENT_EVENTS`); joins, finished tests and payments are
    counted on the server, where they cannot be claimed. 204 whether or not
    it was kept: an unsigned request is simply not counted, and an arrival
    is counted once a day per person.
    """
    if body.name not in analytics.CLIENT_EVENTS:
        raise HTTPException(status_code=422, detail="not an event the app reports")
    user_id = _telegram_id(authorization)
    if user_id is None:
        return Response(status_code=204)
    source = body.source if body.name == "app_open" else None
    if body.name == "app_open":
        await analytics.track_arrival(user_id, source)
    else:
        await analytics.track(body.name, user_id, body.detail)
    return Response(status_code=204)


def _signed_user(authorization: str | None) -> dict[str, Any] | None:
    """The Telegram user a Mini App request is signed for, or None."""
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return None
    try:
        user: dict[str, Any] = validate_init_data(init_data, settings.telegram_bot_token)["user"]
        int(user["id"])
        return user
    except (InitDataError, KeyError, TypeError, ValueError):
        return None


@app.post("/api/me", dependencies=[Depends(throttle("events"))])
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """The person holding the app, as the app boots.

    Makes their row if it is missing and brings their names up to date, the
    way the bot's /start does: a partner who only ever opened the app, from
    an invite, used to have no row at all, so nothing could remember who
    they play with or credit whoever invited them - and a row made at boot
    is what dates them as a newcomer. Answers with their partner's first
    name and whether Telegram lets the bot write to them
    (`allows_write_to_pm`), which is what the app's «Разрешить сообщения»
    asks for.
    """
    user = _signed_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    async with get_db() as session:
        await UserRepository.ensure(
            session,
            int(user["id"]),
            first_name=user.get("first_name"),
            username=user.get("username"),
            last_name=user.get("last_name"),
            language=user.get("language_code"),
        )
        partner = await UserRepository.partner_of(session, int(user["id"]))
        partner_name = partner.first_name if partner else None
    return {
        "can_write": bool(user.get("allows_write_to_pm")),
        "partner": {"name": partner_name} if partner_name else None,
    }


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
        # The access product (or, for an invited user, the discounted page)
        # and its price: the same link the bot's purchase button carries.
        access["payment_url"] = await purchase_url_for(referred)
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
    room: str | None = None,
    authorization: str | None = Header(default=None),
) -> Response:
    """
    One card rendered as a branded share image (JPEG).

    Free-preview cards are public; cards past the free prefix require the
    same paid initData as the full question list - or, with `room`, a seat
    in a room that has dealt the caller this card: the partner who did not
    pay plays a paid room's whole deck and may share it like the one who did.
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

    if not is_index_free(idx) and not await _request_is_paid(authorization) and not (
        room and await room_dealt_card(
            room, authorization, theme_enum, level or None, content_type, idx
        )
    ):
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
async def tribute_webhook(request: Request, background: BackgroundTasks) -> JSONResponse:
    """
    Handle incoming Tribute webhook events.

    The service verifies the signature before it touches the database and
    records only deliveries it actually processed, so a rejected one can be
    retried; see `services.apply_webhook_event`. This layer bounds the body,
    parses it, and translates the result into a status code - and, for a
    purchase of the buyer's own, tells the buyer in the chat.
    """
    try:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_WEBHOOK_BODY:
            raise HTTPException(status_code=413, detail="payload too large")

        # Read the body as a stream and stop at the limit. A chunked request
        # carries no Content-Length to refuse up front, and `request.body()`
        # read all of it before the size was checked: 200 MB went into the
        # memory of the process that also runs the bot (audit B-11).
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_WEBHOOK_BODY:
                raise HTTPException(status_code=413, detail="payload too large")
            chunks.append(chunk)
        raw_body = b"".join(chunks)

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

        # Parse JSON payload (from the bytes already read: the stream is spent)
        try:
            payload = json.loads(raw_body)
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
                # 503 is "not applied, send it again", which is what Tribute's
                # retry is for; anything else unexpected is a 500.
                raise HTTPException(
                    status_code=status_code if status_code == 503 else 500,
                    detail=result["message"],
                )

        # «Всё открыто», in the chat, for a grant of the buyer's own: never
        # for a gift (the buyer holds a certificate to hand on), a renewal
        # (nothing new opened), a duplicate (no action), a revoke or an event
        # nobody knows. After the answer, not before it: the message is a
        # getMe and a sendMessage, and Tribute should not wait on Telegram to
        # hear that we have the money.
        buyer = result.get("telegram_user_id")
        if (
            result.get("action") == "grant" and buyer
            and not result.get("gift") and not result.get("renewal")
        ):
            background.add_task(
                notify_access_granted, int(buyer), bool(result.get("lifetime", True))
            )

        # Counted for /stats after the answer, like the message: a gift, a
        # purchase of one's own (a renewal is not a new one), or a refund.
        if buyer and result.get("action") == "grant" and result.get("gift"):
            background.add_task(analytics.track, "gift_purchase", int(buyer))
        elif buyer and result.get("action") == "grant" and not result.get("renewal"):
            background.add_task(
                analytics.track, "purchase", int(buyer),
                "lifetime" if result.get("lifetime", True) else "period",
            )
        elif buyer and result.get("action") == "revoke":
            background.add_task(analytics.track, "refund", int(buyer))

        # What was done, in the reply Tribute's delivery log keeps: an
        # operator reading "ignore" there learns more than "success", and
        # the note says why (a stale event, nothing to cancel).
        content = {"status": result["status"], "message": result["message"]}
        if "action" in result:
            content["action"] = result["action"]
        if result.get("note"):
            content["note"] = result["note"]
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

    # Bytes, for the same reason as in webapp_auth: a non-ASCII token must be
    # a wrong token, not a TypeError.
    if not hmac.compare_digest(token.encode("utf-8", "replace"), secret.encode("utf-8")):
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
    app.mount(
        "/app",
        CachedStaticFiles(directory=str(WEBAPP_DIR), html=True, cache_control=_webapp_cache_control),
        name="webapp",
    )
else:
    logger.warning(f"Mini App directory not found: {WEBAPP_DIR}")

# The Mini App renders on the same card art the bot composites onto, so
# it needs the PNGs themselves. Read-only and public: these are the same
# images every user already receives as photos.
if ASSETS_DIR.exists():
    app.mount(
        "/assets",
        CachedStaticFiles(directory=str(ASSETS_DIR), cache_control=lambda _path: ASSET_CACHE),
        name="assets",
    )
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

