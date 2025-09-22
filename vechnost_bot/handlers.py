"""Message and callback handlers for the Vechnost bot."""

import logging
from typing import Any

from telegram import InputMediaPhoto, Update
from telegram.ext import ContextTypes

from .i18n import Language, get_text, detect_language_from_text
from .monitoring import (
    log_bot_event,
    log_callback_event,
    log_session_event,
    set_user_context,
    track_errors,
    track_performance,
)
from .keyboards import (
    get_calendar_keyboard,
    get_level_keyboard,
    get_nsfw_confirmation_keyboard,
    get_question_keyboard,
    get_reset_confirmation_keyboard,
    get_theme_keyboard,
)
from .language_keyboards import get_language_selection_keyboard
from .logic import load_game_data
from .models import ContentType, SessionState, Theme
from .renderer import get_background_path, render_card
from .storage import get_session, reset_session

logger = logging.getLogger(__name__)

# Load game data once at module level
GAME_DATA = load_game_data()


@track_performance("start_command")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Set user context for monitoring
    set_user_context(user_id, username)

    logger.info(f"Start command received from chat {update.effective_chat.id}")
    log_bot_event("start_command", user_id=user_id, username=username)

    # Detect language from user's message or default to Russian
    detected_language = detect_language_from_text(update.message.text or "")

    welcome_text = f"{get_text('welcome.title', detected_language)}\n\n{get_text('welcome.subtitle', detected_language)}\n\n{get_text('welcome.prompt', detected_language)}"

    keyboard = get_language_selection_keyboard(detected_language)
    logger.info(f"Sending language selection keyboard with {len(keyboard.inline_keyboard)} rows")

    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if not update.message:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    language = session.language

    help_text = f"{get_text('help.title', language)}\n\n{get_text('help.themes', language)}{get_text('help.how_to_play', language)}{get_text('help.commands', language)}"

    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /reset command."""
    if not update.message:
        return

    # Get session to determine language
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    language = session.language

    reset_text = f"{get_text('reset.title', language)}\n\n{get_text('reset.confirm_text', language)}"

    await update.message.reply_text(
        reset_text,
        reply_markup=get_reset_confirmation_keyboard(language)
    )


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

    # Use the new callback handler registry
    from .callback_handlers import callback_registry
    await callback_registry.handle_callback(query, data)


async def show_theme_selection(query: Any) -> None:
    """Show theme selection menu."""
    welcome_text = WELCOME_PROMPT

    # Handle both text and photo messages
    try:
        await query.edit_message_text(
            welcome_text,
            reply_markup=get_theme_keyboard()
        )
    except Exception as edit_error:
        logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
        # Delete the current message (photo) and send a new text message
        try:
            await query.message.delete()
        except Exception as delete_error:
            logger.warning(f"Could not delete message: {delete_error}")
        await query.message.reply_text(
            welcome_text,
            reply_markup=get_theme_keyboard()
        )


async def handle_theme_selection(query: Any, data: str, session: SessionState) -> None:
    """Handle theme selection."""
    theme_name = data.replace("theme_", "")
    try:
        theme = Theme(theme_name)
    except ValueError:
        await query.edit_message_text(ERROR_INVALID_THEME)
        return

    session.theme = theme

    # Check if NSFW confirmation is needed
    if GAME_DATA.has_nsfw_content(theme) and not session.is_nsfw_confirmed:
        nsfw_text = f"{NSFW_WARNING_TITLE}\n\n{NSFW_WARNING_TEXT}"

        await query.edit_message_text(
            nsfw_text,
            reply_markup=get_nsfw_confirmation_keyboard()
        )
        return

    # Handle different theme types
    if theme == Theme.SEX:
        # Sex: Show calendar immediately with toggle
        session.content_type = ContentType.QUESTIONS
        await show_sex_calendar(query, session, 0, ContentType.QUESTIONS)
    elif theme == Theme.PROVOCATION:
        # Provocation: Show calendar immediately
        session.content_type = ContentType.QUESTIONS
        await show_calendar(query, session, 0, ContentType.QUESTIONS)
    else:
        # Acquaintance, For Couples: Show level selection
        available_levels = GAME_DATA.get_available_levels(theme)
        if not available_levels:
            await query.edit_message_text("❌ Уровни недоступны для этой темы.")
            return
        await show_level_selection(query, theme, available_levels)


async def show_level_selection(query: Any, theme: Theme, available_levels: list[int]) -> None:
    """Show level selection menu."""
    theme_names = {
        Theme.ACQUAINTANCE: Theme.ACQUAINTANCE.value_short(),
        Theme.FOR_COUPLES: Theme.FOR_COUPLES.value_short(),
        Theme.SEX: Theme.SEX.value_short(),
        Theme.PROVOCATION: Theme.PROVOCATION.value_short(),
    }

    theme_emojis = {
        Theme.ACQUAINTANCE: "🤝",
        Theme.FOR_COUPLES: "💕",
        Theme.SEX: "🔥",
        Theme.PROVOCATION: "⚡",
    }

    emoji = theme_emojis.get(theme, "🎴")
    theme_name = theme_names.get(theme, theme.value)
    level_text = f"{emoji} {theme_name}\n\n{LEVEL_PROMPT}"

    # Handle both text and photo messages
    try:
        await query.edit_message_text(
            level_text,
            reply_markup=get_level_keyboard(theme, available_levels)
        )
    except Exception as edit_error:
        logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
        # Delete the current message (photo) and send a new text message
        try:
            await query.message.delete()
        except Exception as delete_error:
            logger.warning(f"Could not delete message: {delete_error}")
        await query.message.reply_text(
            level_text,
            reply_markup=get_level_keyboard(theme, available_levels)
        )


async def handle_level_selection(query: Any, data: str, session: SessionState) -> None:
    """Handle level selection."""
    level = int(data.replace("level_", ""))
    session.level = level

    if not session.theme:
        await query.edit_message_text(ERROR_NO_THEME)
        return

    # Set content type and show calendar for the selected level
    session.content_type = ContentType.QUESTIONS
    await show_calendar(query, session, 0, ContentType.QUESTIONS)


async def show_calendar(query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
    """Show calendar for questions/tasks."""
    if not session.theme:
        await query.edit_message_text(ERROR_NO_THEME)
        return

    # Get topic code
    topic_codes = {
        Theme.ACQUAINTANCE: "acq",
        Theme.FOR_COUPLES: "couples",
        Theme.SEX: "sex",
        Theme.PROVOCATION: "prov"
    }
    topic_code = topic_codes.get(session.theme, "unknown")

    # Get level (0 if no levels)
    level_or_0 = session.level if session.level is not None else 0

    # Get category code
    category = "q" if content_type == ContentType.QUESTIONS else "t"

    # Get items
    items = GAME_DATA.get_content(session.theme, session.level, content_type)
    if not items:
        await query.edit_message_text("❌ Контент недоступен.")
        return

    # Calculate total pages
    items_per_page = 28
    total_pages = (len(items) + items_per_page - 1) // items_per_page

    # Ensure page is within bounds
    page = max(0, min(page, total_pages - 1))

    # Build header text
    if session.theme == Theme.SEX:
        if content_type == ContentType.QUESTIONS:
            header = CALENDAR_SEX_QUESTIONS
        else:
            header = CALENDAR_SEX_TASKS
    else:
        theme_names = {
            Theme.ACQUAINTANCE: TOPIC_ACQUAINTANCE,
            Theme.FOR_COUPLES: TOPIC_FOR_COUPLES,
            Theme.PROVOCATION: TOPIC_PROVOCATION,
        }
        theme_name = theme_names.get(session.theme, session.theme.value)
        if session.level:
            header = f"{theme_name} — Уровень {session.level}"
        else:
            header = f"{theme_name} — {CALENDAR_HEADER}"

    # Show toggle only for Sex theme
    show_toggle = (session.theme == Theme.SEX)

    keyboard = get_calendar_keyboard(
        topic_code, level_or_0, category, page, items, total_pages, show_toggle
    )

    # Handle both text and photo messages
    try:
        await query.edit_message_text(header, reply_markup=keyboard)
    except Exception as edit_error:
        logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
        # Delete the current message (photo) and send a new text message
        try:
            await query.message.delete()
        except Exception as delete_error:
            logger.warning(f"Could not delete message: {delete_error}")
        await query.message.reply_text(header, reply_markup=keyboard)


async def show_sex_calendar(query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
    """Show Sex calendar with toggle."""
    await show_calendar(query, session, page, content_type)


async def handle_calendar_page(query: Any, data: str, session: SessionState) -> None:
    """Handle calendar page navigation."""
    # Parse: cal:{topic}:{level_or_0}:{category}:{page}
    parts = data.split(":")
    if len(parts) != 5:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    topic_code = parts[1]
    level_or_0 = int(parts[2])
    category = parts[3]
    page = int(parts[4])

    # Convert topic code to theme
    topic_to_theme = {
        "acq": Theme.ACQUAINTANCE,
        "couples": Theme.FOR_COUPLES,
        "sex": Theme.SEX,
        "prov": Theme.PROVOCATION
    }

    theme = topic_to_theme.get(topic_code)
    if not theme:
        await query.edit_message_text(ERROR_INVALID_THEME)
        return

    # Set session state
    session.theme = theme
    session.level = level_or_0 if level_or_0 > 0 else None

    # Convert category to content type
    content_type = ContentType.QUESTIONS if category == "q" else ContentType.TASKS

    # Show calendar
    await show_calendar(query, session, page, content_type)


async def handle_question_selection(query: Any, data: str, session: SessionState) -> None:
    """Handle question selection from calendar."""
    # Parse: q:{topic}:{level_or_0}:{index}
    parts = data.split(":")
    if len(parts) != 4:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    topic_code = parts[1]
    level_or_0 = int(parts[2])
    index = int(parts[3])

    # Convert topic code to theme
    topic_to_theme = {
        "acq": Theme.ACQUAINTANCE,
        "couples": Theme.FOR_COUPLES,
        "sex": Theme.SEX,
        "prov": Theme.PROVOCATION
    }

    theme = topic_to_theme.get(topic_code)
    if not theme:
        await query.edit_message_text(ERROR_INVALID_THEME)
        return

    # Set session state
    session.theme = theme
    session.level = level_or_0 if level_or_0 > 0 else None

    # Get content type from current session or default to questions
    content_type = session.content_type

    # Get items
    items = GAME_DATA.get_content(theme, session.level, content_type)
    if not items or index >= len(items):
        await query.edit_message_text("❌ Вопрос недоступен.")
        return

    # Get the question
    question = items[index]

    # Build header
    header = QUESTION_HEADER.format(current=index+1, total=len(items))

    # Show question with navigation
    keyboard = get_question_keyboard(topic_code, level_or_0, index, len(items))

    # Try to render as image, fallback to text if it fails
    try:
        # Get background path
        bg_path = get_background_path(topic_code, level_or_0, "q" if content_type == ContentType.QUESTIONS else "t")
        logger.info(f"Rendering card with background: {bg_path}")

        # Render card image
        image_data = render_card(question, bg_path)
        logger.info(f"Card rendered successfully, size: {len(image_data.getvalue())} bytes")

        # Try to edit message to photo, fallback to new message if that fails
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=image_data),
                reply_markup=keyboard
            )
        except Exception as edit_error:
            logger.warning(f"Could not edit message to photo: {edit_error}, sending new message")
            # Fallback: send new photo message
            await query.message.reply_photo(
                photo=image_data,
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error rendering card image: {e}", exc_info=True)
        # Fallback to text message
        await query.edit_message_text(
            f"{header}\n\n{question}",
            reply_markup=keyboard
        )


async def handle_question_navigation(query: Any, data: str, session: SessionState) -> None:
    """Handle navigation between questions."""
    # Parse: nav:{topic}:{level_or_0}:{index}
    parts = data.split(":")
    if len(parts) != 4:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    topic_code = parts[1]
    level_or_0 = int(parts[2])
    index = int(parts[3])

    # Convert topic code to theme
    topic_to_theme = {
        "acq": Theme.ACQUAINTANCE,
        "couples": Theme.FOR_COUPLES,
        "sex": Theme.SEX,
        "prov": Theme.PROVOCATION
    }

    theme = topic_to_theme.get(topic_code)
    if not theme:
        await query.edit_message_text(ERROR_INVALID_THEME)
        return

    # Set session state
    session.theme = theme
    session.level = level_or_0 if level_or_0 > 0 else None

    # Get content type from current session or default to questions
    content_type = session.content_type

    # Get items
    items = GAME_DATA.get_content(theme, session.level, content_type)
    if not items or index >= len(items):
        await query.edit_message_text("❌ Вопрос недоступен.")
        return

    # Get the question
    question = items[index]

    # Build header
    header = QUESTION_HEADER.format(current=index+1, total=len(items))

    # Show question with navigation
    keyboard = get_question_keyboard(topic_code, level_or_0, index, len(items))

    # Try to render as image, fallback to text if it fails
    try:
        # Get background path
        bg_path = get_background_path(topic_code, level_or_0, "q" if content_type == ContentType.QUESTIONS else "t")
        logger.info(f"Rendering card with background: {bg_path}")

        # Render card image
        image_data = render_card(question, bg_path)
        logger.info(f"Card rendered successfully, size: {len(image_data.getvalue())} bytes")

        # Try to edit message to photo, fallback to new message if that fails
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=image_data),
                reply_markup=keyboard
            )
        except Exception as edit_error:
            logger.warning(f"Could not edit message to photo: {edit_error}, sending new message")
            # Fallback: send new photo message
            await query.message.reply_photo(
                photo=image_data,
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error rendering card image: {e}", exc_info=True)
        # Fallback to text message
        await query.edit_message_text(
            f"{header}\n\n{question}",
            reply_markup=keyboard
        )


async def handle_toggle_content(query: Any, data: str, session: SessionState) -> None:
    """Handle toggling between questions and tasks (Sex only)."""
    # Parse: toggle:sex:{category}:{page}
    parts = data.split(":")
    if len(parts) != 4:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    topic_code = parts[1]  # Should be "sex"
    category = parts[2]    # "q" or "t"
    page = int(parts[3])

    if topic_code != "sex":
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    # Set session state
    session.theme = Theme.SEX
    session.level = None  # Sex has no levels

    # Convert category to content type
    content_type = ContentType.QUESTIONS if category == "q" else ContentType.TASKS
    session.content_type = content_type

    # Show calendar
    await show_sex_calendar(query, session, page, content_type)


async def handle_back_navigation(query: Any, data: str, session: SessionState) -> None:
    """Handle back navigation."""
    # Parse: back:{where}
    parts = data.split(":")
    if len(parts) != 2:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)
        return

    where = parts[1]
    logger.info(f"Back navigation to: {where}, theme: {session.theme}, level: {session.level}")

    if where == "themes":
        await show_theme_selection(query)
    elif where == "levels":
        if not session.theme:
            await show_theme_selection(query)
            return
        available_levels = GAME_DATA.get_available_levels(session.theme)
        if available_levels:
            await show_level_selection(query, session.theme, available_levels)
        else:
            await show_theme_selection(query)
    elif where == "calendar":
        # Go back to calendar - need to determine which calendar
        if not session.theme:
            await show_theme_selection(query)
            return

        # Determine current page (default to 0)
        current_page = 0

        if session.theme == Theme.SEX:
            # For Sex, show the current content type
            content_type = session.content_type
            await show_sex_calendar(query, session, current_page, content_type)
        else:
            # For other themes, show questions calendar
            await show_calendar(query, session, current_page, ContentType.QUESTIONS)
    else:
        await query.edit_message_text(ERROR_UNKNOWN_CALLBACK)


async def handle_nsfw_confirmation(query: Any, session: SessionState) -> None:
    """Handle NSFW content confirmation."""
    session.is_nsfw_confirmed = True

    if not session.theme:
        await query.edit_message_text(ERROR_NO_THEME)
        return

    # For Sex theme, show calendar immediately
    if session.theme == Theme.SEX:
        session.content_type = ContentType.QUESTIONS
        await show_sex_calendar(query, session, 0, ContentType.QUESTIONS)
    else:
        # For other themes, show level selection
        available_levels = GAME_DATA.get_available_levels(session.theme)
        if available_levels:
            await show_level_selection(query, session.theme, available_levels)
        else:
            await show_theme_selection(query)


async def handle_nsfw_denial(query: Any) -> None:
    """Handle NSFW content denial."""
    await query.edit_message_text(
        NSFW_ACCESS_DENIED,
        reply_markup=get_theme_keyboard()
    )


async def handle_reset_request(query: Any) -> None:
    """Handle reset game request."""
    reset_text = f"{RESET_TITLE}\n\n{RESET_CONFIRM_TEXT}"

    await query.edit_message_text(
        reset_text,
        reply_markup=get_reset_confirmation_keyboard()
    )


async def handle_reset_confirmation(query: Any, session: SessionState) -> None:
    """Handle reset confirmation."""
    reset_session(query.message.chat.id)

    await query.edit_message_text(
        RESET_COMPLETED,
        reply_markup=get_theme_keyboard()
    )


async def handle_reset_cancel(query: Any, session: SessionState) -> None:
    """Handle reset cancellation."""
    await query.edit_message_text(
        RESET_CANCELLED,
        reply_markup=get_theme_keyboard()
    )
