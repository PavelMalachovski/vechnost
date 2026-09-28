"""Message and callback handlers for the Vechnost bot.

Command handlers live here; all inline-keyboard callbacks are routed through
the handler registry in callback_handlers.py.
"""

import html
import logging
import re
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
    WebAppInfo,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .callback_handlers import features_block, welcome_screen
from .config import settings
from .i18n import Language, get_text
from .keyboards import get_reset_confirmation_keyboard
from .monitoring import (
    log_bot_event,
    log_callback_event,
    set_user_context,
    track_performance,
)
from .paths import ASSETS
from .storage import get_session

logger = logging.getLogger(__name__)


async def _send_invite_button(message: Message, screen: str, code: str) -> bool:
    """Answer an invite link with the button that opens it. False if we can't.

    False means there is no Mini App URL configured to send anyone to, and
    the caller falls through to the ordinary welcome screen: a partner who
    followed a link must never end up staring at nothing.

    Takes the message rather than the update: the caller has already
    established there is one, and reaching back through `message`
    here only loses that.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from .config import settings

    url = settings.webapp_join_url(screen, code)
    if not url:
        logger.warning("Invite link received but WEBAPP_URL is unset")
        return False

    kind = {"steps69": "s69", "compat": "compat", "coop": "coop"}[screen]
    language = Language.RUSSIAN
    text = f"{get_text(f'invite.{kind}_title', language)}\n\n{get_text('invite.hint', language)}"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text(f"invite.{kind}_button", language),
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )
    await message.reply_text(text, reply_markup=keyboard)
    # The screen only: the code is a seat in someone's game while it is open.
    logger.info(f"Invite link opened: {screen}")
    return True


@track_performance("start_command")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    # `effective_user` is not merely a convenience for `message.from_user`:
    # it is genuinely absent on a message posted on behalf of a channel in a
    # linked discussion group, where Telegram sends `sender_chat` and no
    # `from`. Reading `.id` off it was an AttributeError waiting for someone
    # to type /start as their channel. There is nobody to greet in that case,
    # so there is nothing to do but return.
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None:
        return

    user_id = user.id

    # Set user context for monitoring
    set_user_context(user_id)

    # Whether there was a parameter, never what it was: a /start argument
    # can be a gift certificate code, which is lifetime access to whoever
    # reads the log.
    logger.info(
        f"Start command received from chat {chat.id} (with parameter: {bool(context.args)})"
    )
    log_bot_event("start_command", user_id=user_id)

    # Register the user on plain /start, not only on the referral and
    # /invite paths: the daily card selects its recipients from the users
    # table, and before this line most people who simply pressed /start and
    # played in the Mini App were never in it. Swallows its own errors, so
    # a database hiccup cannot take /start down.
    from .payments.middleware import check_and_register_user

    await check_and_register_user(update, context)

    # Counted for /stats: an arrival, and the channel it came by - a
    # `src_<tag>` link, a referral, an invite, a gift - never the parameter
    # itself, which can be a certificate code.
    from .analytics import arrival_source, track

    await track(
        "bot_start",
        user_id,
        source=arrival_source(context.args[0] if context.args else None),
    )

    # Check for certificate activation parameter
    if context.args and len(context.args) > 0:
        param = context.args[0]
        logger.info(f"Start command parameter kind: {param.partition('_')[0]!r}")

        # A referral link. Credited before the greeting and never instead of
        # it: whoever followed the link came to see the bot, and a failed
        # credit (their own link, a second link, an unknown code, or an
        # account that was here before the link - see `record_referral`)
        # must still leave them on the welcome screen, and says nothing.
        from .referrals import parse_start_param

        referral_code = parse_start_param(param)
        if referral_code:
            try:
                from .payments.database import get_db
                from .payments.repositories import UserRepository

                async with get_db() as db_session:
                    await UserRepository.create_or_update(
                        db_session,
                        telegram_user_id=user_id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        language=user.language_code,
                    )
                    credited = await UserRepository.record_referral(
                        db_session, user_id, referral_code
                    )
                if credited:
                    # The discount is only promised when it exists: with
                    # REFERRAL_PAYMENT_URL unset the codes are still minted
                    # and invites recorded, but there is no discounted
                    # payment page to send anyone to. And `percent` must be
                    # passed, or the reader sees a literal "{percent}".
                    from .config import settings as _settings
                    from .referrals import discount_available

                    if discount_available():
                        await message.reply_text(
                            get_text(
                                "referral.welcome",
                                Language.RUSSIAN,
                                percent=_settings.referral_discount_percent,
                            )
                        )
                    else:
                        await message.reply_text(
                            get_text("referral.welcome_no_discount", Language.RUSSIAN)
                        )
            except Exception as e:
                logger.warning(f"Referral not credited: {e}")

        # An invite link: `?start=s69_XXXXXX` and its two siblings. Whoever
        # tapped it came to join something, not to read the greeting, so the
        # answer is one button that opens the app already holding the code.
        # (With a Mini App short name configured the tap never reaches the
        # bot at all — Telegram opens the app directly.)
        from .invites import parse_invite_param

        invite = parse_invite_param(param)
        if invite:
            screen, code = invite
            if await _send_invite_button(message, screen, code):
                return

        if param.startswith("activate_"):
            # A gift's card or a printed voucher's QR: asked, not done on
            # the spot (`ask_to_activate`).
            logger.info("Certificate activation via deep link")
            await ask_to_activate(message, user_id, param.removeprefix("activate_"))
            return

    # There is nothing to choose any more: open straight on the greeting.
    # The logo goes first, as its own message and without a caption — the
    # greeting runs to about two thousand characters and Telegram caps photo
    # captions at 1024, so it cannot ride along, and every section added to
    # it moves further from the cap rather than nearer. A missing or
    # unreadable logo must not take /start down, hence the fallback to the
    # greeting alone.
    try:
        with open(ASSETS / "images" / "vechnost_logo.png", "rb") as logo_file:
            await message.reply_photo(photo=logo_file)
    except Exception as e:
        logger.warning(f"Failed to load logo image: {e}, sending greeting only")

    text, keyboard = welcome_screen(Language.RUSSIAN)
    await message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/invite`: the user's own referral link, and what it is worth."""
    if not update.message or not update.effective_user:
        return

    from .config import settings
    from .payments.database import get_db
    from .payments.repositories import UserRepository
    from .referrals import discount_available, invite_link

    user_id = update.effective_user.id
    language = Language.RUSSIAN

    try:
        async with get_db() as session:
            await UserRepository.create_or_update(
                session,
                telegram_user_id=user_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                can_message=True,
            )
            code = await UserRepository.ensure_referral_code(session, user_id)
            invited = await UserRepository.count_referrals(session, user_id)
    except Exception as e:
        logger.error(f"Could not build an invite link for {user_id}: {e}")
        await update.message.reply_text(get_text("referral.error", language))
        return

    link = invite_link(code) if code else None
    if not link:
        await update.message.reply_text(get_text("referral.error", language))
        return

    text = get_text(
        "referral.invite" if discount_available() else "referral.invite_no_discount",
        language,
        link=link,
        percent=settings.referral_discount_percent,
        invited=invited,
    )
    await update.message.reply_text(text, disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if not update.message or not update.effective_chat:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = await get_session(chat_id)
    language = session.language

    help_text = f"{get_text('help.title', language)}\n\n{get_text('help.themes', language)}{get_text('help.how_to_play', language)}{get_text('help.commands', language)}"

    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /reset command."""
    if not update.message or not update.effective_chat:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = await get_session(chat_id)
    language = session.language

    reset_text = (
        f"{get_text('reset.title', language)}\n\n{get_text('reset.confirm_text', language)}"
    )

    await update.message.reply_text(
        reset_text, reply_markup=get_reset_confirmation_keyboard(language)
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /about command - show information about the bot."""
    if not update.message or not update.effective_chat:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = await get_session(chat_id)
    language = session.language

    # Build about message
    about_text = (
        f"{get_text('about.title', language)}\n\n"
        f"{get_text('about.intro', language)}\n\n"
        f"{get_text('about.features_title', language)}\n\n"
        f"{get_text('about.feature_themes', language)}\n"
        f"{get_text('about.feature_themes_desc', language)}\n\n"
        f"{get_text('about.feature_levels', language)}\n"
        f"{get_text('about.feature_levels_desc', language)}\n\n"
        f"{get_text('about.feature_questions', language)}\n"
        f"{get_text('about.feature_questions_desc', language)}\n\n"
        f"{get_text('about.feature_tasks', language)}\n"
        f"{get_text('about.feature_tasks_desc', language)}\n\n"
        # The board, the masterclass, the compatibility test and the library,
        # from the same block the welcome screen reads. Plain text here: this
        # message is sent without a parse mode.
        f"{features_block(language)}\n\n"
        f"{get_text('about.feature_privacy', language)}\n"
        f"{get_text('about.feature_privacy_desc', language)}\n\n"
        f"{get_text('about.how_it_works', language)}\n"
        f"{get_text('about.step1', language)}\n"
        f"{get_text('about.step2', language)}\n"
        f"{get_text('about.step3', language)}\n"
        f"{get_text('about.step4', language)}\n\n"
        f"{get_text('about.perfect_for', language)}\n"
        f"{get_text('about.perfect_first_date', language)}\n"
        f"{get_text('about.perfect_long_relationship', language)}\n"
        f"{get_text('about.perfect_crisis', language)}\n"
        f"{get_text('about.perfect_spice', language)}\n"
        f"{get_text('about.perfect_deep_talks', language)}\n\n"
        f"{get_text('about.cta', language)}"
    )

    await update.message.reply_text(about_text)


@track_performance("activate_certificate")
async def activate_certificate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /activate command for certificate activation."""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None:
        return

    user_id = user.id

    # Set user context for monitoring
    set_user_context(user_id)

    logger.info(f"Activate certificate command received from user {user_id}")
    log_bot_event("activate_certificate_command", user_id=user_id)

    # Get session to determine language
    session = await get_session(chat.id)
    language = session.language

    # Get certificate code from command arguments
    if not context.args or len(context.args) == 0:
        # No code provided. HTML: the text is bold-headed, and its
        # placeholder is escaped in the YAML for exactly this parse mode.
        help_text = get_text("certificate.usage", language)
        await message.reply_text(help_text, parse_mode="HTML")
        return

    code = context.args[0].strip().upper()

    # Activate certificate with full user information
    from .payments.services import activate_certificate

    result = await activate_certificate(
        code=code,
        telegram_user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    text, keyboard = activation_reply(result, language)
    await message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


def _app_keyboard(language: Language) -> InlineKeyboardMarkup | None:
    """The one button into the Mini App, or None where there is no app."""
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("welcome.button_webapp", language),
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )


def activation_reply(
    result: dict[str, Any], language: Language
) -> tuple[str, InlineKeyboardMarkup | None]:
    """What the bot answers an activation with, from /activate or a link."""
    if result["status"] == "success":
        return get_text("certificate.activated", language), _app_keyboard(language)
    if result.get("code") == 409 and result.get("yours"):
        return get_text("certificate.already_yours", language), _app_keyboard(language)
    key = {
        404: "certificate.not_found",
        409: "certificate.already_used",
        410: "certificate.revoked",
    }.get(result.get("code"), "certificate.error")  # type: ignore[arg-type]
    return get_text(key, language), None


# The two buttons under «activate this?». The code is not in them.
ACTIVATE = "gift_activate"
NOT_NOW = "gift_later"
ACTIVATE_PATTERN = f"^({ACTIVATE}|{NOT_NOW})$"


async def ask_to_activate(message: Message, user_id: int, raw_code: str) -> None:
    """The question a gift's or a voucher's link opens on.

    Never activated on the spot: the first person to open a gift's link is
    usually its buyer, checking it, and a code activates once, for whoever
    gets there first. The code rides in the question's own text, which the
    button reads back (`activate_callback`) - never in callback data, which
    the callback registry logs, and a code is lifetime access to whoever
    reads it.
    """
    from .payments.services import user_has_access

    code = raw_code.strip().upper()
    text = get_text("gift.confirm", Language.RUSSIAN, code=html.escape(code))
    if await user_has_access(user_id):
        text += get_text("gift.confirm_has_access", Language.RUSSIAN)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("gift.activate_button", Language.RUSSIAN), callback_data=ACTIVATE
                ),
                InlineKeyboardButton(
                    get_text("gift.later_button", Language.RUSSIAN), callback_data=NOT_NOW
                ),
            ]
        ]
    )
    await message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


def _code_in(message: object) -> str | None:
    """The code a question carries, read back from its own text: the
    `<code>` it was set in, else the shape a code has."""
    parse = getattr(message, "parse_entities", None)
    if parse is not None:
        codes = list(parse([MessageEntity.CODE]).values())
        if codes:
            return str(codes[0]).strip().upper()
    match = _CERTIFICATE_CODE.search(getattr(message, "text", None) or "")
    if match:
        return f"VECH-{match.group(1)}-{match.group(2)}".upper()
    return None


async def activate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«Активировать» or «Не сейчас» under the question."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()
    language = Language.RUSSIAN
    keyboard: InlineKeyboardMarkup | None = None
    if query.data == NOT_NOW:
        text = get_text("gift.later", language)
    else:
        code = _code_in(query.message)
        if code is None:
            # The question is too old to read back: the command still works.
            text = get_text("certificate.usage", language)
        else:
            from .payments.services import activate_certificate

            user = query.from_user
            result = await activate_certificate(
                code=code,
                telegram_user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            text, keyboard = activation_reply(result, language)
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest:
        if isinstance(query.message, Message):
            await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


# A gift or voucher code as people paste it: `VECH-XXXX-XXXX`, in any case,
# with or without its dashes, often inside a sentence.
_CERTIFICATE_CODE = re.compile(
    r"(?<![A-Za-z0-9])VECH[-\s]?([A-Z0-9]{4})[-\s]?([A-Z0-9]{4})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


async def write_access_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram's word that the bot may now write to this person.

    A service message, sent when someone allows the bot to message them
    from a Mini App - its `requestWriteAccess`, or the checkbox on opening
    one from a link - without ever pressing /start. It marks them reachable
    (`User.can_message`) so the pushes they allowed reach them, and says
    nothing back: the person is in the app, not in this chat.
    """
    from .payments.middleware import check_and_register_user

    await check_and_register_user(update, context)


async def free_text_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer text that no command or button asked for.

    The bot is driven by buttons and commands, and anything else used to
    get no answer at all - including a certificate code pasted on its own,
    which is exactly what someone holding a gift card does first. That
    case gets the command to send, ready to copy; everything else gets a
    pointer to /start and /help. The text itself is never logged: it may
    be a code, and a code is lifetime access to whoever reads it.
    """
    message = update.message
    if message is None or not message.text:
        return

    match = _CERTIFICATE_CODE.search(message.text)
    if match:
        code = f"VECH-{match.group(1).upper()}-{match.group(2).upper()}"
        await message.reply_text(
            get_text("hints.certificate", Language.RUSSIAN, code=code),
            parse_mode="HTML",
        )
        return

    await message.reply_text(get_text("hints.free_text", Language.RUSSIAN))


@track_performance("callback_query")
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    if not query or not query.message or not query.message.chat:
        logger.warning("Callback query received but missing query, message, or chat")
        return

    chat_id = query.message.chat.id
    user_id = update.effective_user.id if update.effective_user else None

    logger.info(f"Callback query received: {query.data} from chat {chat_id}")
    log_callback_event(query.data, user_id or chat_id)

    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")

    data = query.data
    if not data:
        logger.warning("Callback query received with no data")
        return

    # Use the callback handler registry
    from .callback_handlers import callback_registry

    await callback_registry.handle_callback(query, data)
