"""Message and callback handlers for the Vechnost bot.

Command handlers live here; all inline-keyboard callbacks are routed through
the handler registry in callback_handlers.py.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .callback_handlers import welcome_screen
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


async def _send_invite_button(update: Update, screen: str, code: str) -> bool:
    """Answer an invite link with the button that opens it. False if we can't.

    False means there is no Mini App URL configured to send anyone to, and
    the caller falls through to the ordinary welcome screen: a partner who
    followed a link must never end up staring at nothing.
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
    await update.message.reply_text(text, reply_markup=keyboard)
    logger.info(f"Invite link opened: {screen} {code}")
    return True


@track_performance("start_command")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Set user context for monitoring
    set_user_context(user_id, username)

    logger.info(
        f"Start command received from chat {update.effective_chat.id}, "
        f"args: {context.args if context.args else 'None'}"
    )
    log_bot_event("start_command", user_id=user_id, username=username)

    # Check for certificate activation parameter
    if context.args and len(context.args) > 0:
        param = context.args[0]
        logger.info(f"Start command parameter: {param}")

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
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name,
                        language=update.effective_user.language_code,
                    )
                    credited = await UserRepository.record_referral(
                        db_session, user_id, referral_code
                    )
                if credited:
                    await update.message.reply_text(
                        get_text("referral.welcome", Language.RUSSIAN)
                    )
            except Exception as e:
                logger.warning(f"Referral {referral_code} not credited: {e}")

        # An invite link: `?start=s69_XXXXXX` and its two siblings. Whoever
        # tapped it came to join something, not to read the greeting, so the
        # answer is one button that opens the app already holding the code.
        # (With a Mini App short name configured the tap never reaches the
        # bot at all — Telegram opens the app directly.)
        from .invites import parse_invite_param

        invite = parse_invite_param(param)
        if invite:
            screen, code = invite
            if await _send_invite_button(update, screen, code):
                return

        if param.startswith("activate_"):
            # Extract certificate code
            code = param.replace("activate_", "").strip().upper()
            logger.info(f"Certificate activation via deep link: {code}")

            # Activate certificate with full user information
            from .payments.services import activate_certificate

            result = await activate_certificate(
                code=code,
                telegram_user_id=user_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name,
            )

            # Get session to determine language
            chat_id = update.effective_chat.id
            session = await get_session(chat_id)
            language = session.language

            if result["status"] == "success":
                success_text = get_text("certificate.activated", language)
                await update.message.reply_text(success_text, parse_mode="HTML")
                # Continue with normal start flow
            elif result.get("code") == 404:
                error_text = get_text("certificate.not_found", language)
                await update.message.reply_text(error_text)
                return
            elif result.get("code") == 409:
                error_text = get_text("certificate.already_used", language)
                await update.message.reply_text(error_text)
                return
            else:
                error_text = get_text("certificate.error", language)
                await update.message.reply_text(error_text)
                return

    # There is nothing to choose any more: open straight on the greeting.
    # The logo goes first, as its own message and without a caption — the
    # greeting is ~1530 characters and Telegram caps photo captions at 1024,
    # so it cannot ride along. A missing or unreadable logo must not take
    # /start down, hence the fallback to the greeting alone.
    try:
        with open("assets/images/vechnost_logo.png", "rb") as logo_file:
            await update.message.reply_photo(photo=logo_file)
    except Exception as e:
        logger.warning(f"Failed to load logo image: {e}, sending greeting only")

    text, keyboard = welcome_screen(Language.RUSSIAN)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


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
    if not update.message:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = await get_session(chat_id)
    language = session.language

    help_text = f"{get_text('help.title', language)}\n\n{get_text('help.themes', language)}{get_text('help.how_to_play', language)}{get_text('help.commands', language)}"

    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /reset command."""
    if not update.message:
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
    if not update.message:
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
        f"{get_text('about.feature_privacy', language)}\n"
        f"{get_text('about.feature_privacy_desc', language)}\n\n"
        f"{get_text('about.feature_library', language)}\n"
        f"{get_text('about.feature_library_desc', language)}\n\n"
        f"{get_text('about.how_it_works', language)}\n"
        f"{get_text('about.step1', language)}\n"
        f"{get_text('about.step2', language)}\n"
        f"{get_text('about.step3', language)}\n"
        f"{get_text('about.step4', language)}\n\n"
        f"{get_text('about.perfect_for', language)}\n"
        f"{get_text('about.perfect_first_date', language)}\n"
        f"{get_text('about.perfect_long_relationship', language)}\n"
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
    if not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Set user context for monitoring
    set_user_context(user_id, username)

    logger.info(f"Activate certificate command received from user {user_id}")
    log_bot_event("activate_certificate_command", user_id=user_id, username=username)

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = await get_session(chat_id)
    language = session.language

    # Get certificate code from command arguments
    if not context.args or len(context.args) == 0:
        # No code provided
        help_text = get_text("certificate.usage", language)
        await update.message.reply_text(help_text)
        return

    code = context.args[0].strip().upper()

    # Activate certificate with full user information
    from .payments.services import activate_certificate

    result = await activate_certificate(
        code=code,
        telegram_user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
    )

    if result["status"] == "success":
        success_text = get_text("certificate.activated", language)
        await update.message.reply_text(success_text, parse_mode="HTML")
    elif result.get("code") == 404:
        error_text = get_text("certificate.not_found", language)
        await update.message.reply_text(error_text)
    elif result.get("code") == 409:
        error_text = get_text("certificate.already_used", language)
        await update.message.reply_text(error_text)
    else:
        error_text = get_text("certificate.error", language)
        await update.message.reply_text(error_text)


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
