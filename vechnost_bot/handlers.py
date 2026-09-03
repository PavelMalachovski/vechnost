"""Message and callback handlers for the Vechnost bot.

Command handlers live here; all inline-keyboard callbacks are routed through
the handler registry in callback_handlers.py.
"""

import logging

from telegram import Message, Update
from telegram.ext import ContextTypes

from .callback_handlers import features_block, welcome_screen
from .i18n import Language, get_text
from .keyboards import get_reset_confirmation_keyboard
from .monitoring import (
    log_bot_event,
    log_callback_event,
    set_user_context,
    track_performance,
)
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
    text = (
        f"{get_text(f'invite.{kind}_title', language)}\n\n"
        f"{get_text('invite.hint', language)}"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
        get_text(f'invite.{kind}_button', language),
        web_app=WebAppInfo(url=url),
    )]])
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
        f"Start command received from chat {chat.id} "
        f"(with parameter: {bool(context.args)})"
    )
    log_bot_event("start_command", user_id=user_id)

    # Register the user on plain /start, not only on the referral and
    # /invite paths: the daily card selects its recipients from the users
    # table, and before this line most people who simply pressed /start and
    # played in the Mini App were never in it. Swallows its own errors, so
    # a database hiccup cannot take /start down.
    from .payments.middleware import check_and_register_user

    await check_and_register_user(update, context)

    # Check for certificate activation parameter
    if context.args and len(context.args) > 0:
        param = context.args[0]
        logger.info(f"Start command parameter kind: {param.partition('_')[0]!r}")

        # A referral link. Credited before the greeting and never instead of
        # it: whoever followed the link came to see the bot, and a failed
        # credit (their own link, a second link, an unknown code) must still
        # leave them on the welcome screen.
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
            # Extract certificate code
            code = param.replace("activate_", "").strip().upper()
            logger.info("Certificate activation via deep link")

            # Activate certificate with full user information
            from .payments.services import activate_certificate

            result = await activate_certificate(
                code=code,
                telegram_user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )

            # Get session to determine language
            session = await get_session(chat.id)
            language = session.language

            if result["status"] == "success":
                success_text = get_text("certificate.activated", language)
                await message.reply_text(success_text, parse_mode="HTML")
                # Continue with normal start flow
            elif result.get("code") == 404:
                error_text = get_text("certificate.not_found", language)
                await message.reply_text(error_text)
                return
            elif result.get("code") == 409:
                error_text = get_text("certificate.already_used", language)
                await message.reply_text(error_text)
                return
            else:
                error_text = get_text("certificate.error", language)
                await message.reply_text(error_text)
                return

    # There is nothing to choose any more: open straight on the greeting.
    # The logo goes first, as its own message and without a caption — the
    # greeting runs to about two thousand characters and Telegram caps photo
    # captions at 1024, so it cannot ride along, and every section added to
    # it moves further from the cap rather than nearer. A missing or
    # unreadable logo must not take /start down, hence the fallback to the
    # greeting alone.
    try:
        with open("assets/images/vechnost_logo.png", "rb") as logo_file:
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

    reset_text = f"{get_text('reset.title', language)}\n\n{get_text('reset.confirm_text', language)}"

    await update.message.reply_text(
        reset_text,
        reply_markup=get_reset_confirmation_keyboard(language)
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
async def activate_certificate_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
        # No code provided
        help_text = get_text("certificate.usage", language)
        await message.reply_text(help_text)
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

    if result["status"] == "success":
        success_text = get_text("certificate.activated", language)
        await message.reply_text(success_text, parse_mode="HTML")
    elif result.get("code") == 404:
        error_text = get_text("certificate.not_found", language)
        await message.reply_text(error_text)
    elif result.get("code") == 409:
        error_text = get_text("certificate.already_used", language)
        await message.reply_text(error_text)
    else:
        error_text = get_text("certificate.error", language)
        await message.reply_text(error_text)


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
