"""Message and callback handlers for the Vechnost bot."""

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from .keyboards import (
    get_content_type_keyboard,
    get_game_keyboard,
    get_level_keyboard,
    get_nsfw_confirmation_keyboard,
    get_reset_confirmation_keyboard,
    get_theme_keyboard,
)
from .logic import can_draw_card, draw_card, get_remaining_cards_count, load_game_data
from .models import ContentType, SessionState, Theme
from .storage import get_session, reset_session

logger = logging.getLogger(__name__)

# Load game data once at module level
GAME_DATA = load_game_data()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.message:
        return

    logger.info(f"Start command received from chat {update.effective_chat.id}")

    welcome_text = (
        "🎴 Welcome to Vechnost!\n\n"
        "This is an intimate card game designed to deepen your relationships through "
        "meaningful conversations.\n\n"
        "Choose a theme to begin your journey:"
    )

    keyboard = get_theme_keyboard()
    logger.info(f"Sending theme keyboard with {len(keyboard.inline_keyboard)} rows")

    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if not update.message:
        return

    help_text = (
        "🎴 Vechnost Help\n\n"
        "**Themes:**\n"
        "• 🤝 Acquaintance - Get to know each other better\n"
        "• 💕 For Couples - Deepen your relationship\n"
        "• 🔥 Sex - Intimate questions and tasks (18+)\n"
        "• ⚡ Provocation - Challenging scenarios\n\n"
        "**How to play:**\n"
        "1. Choose a theme\n"
        "2. Select a level\n"
        "3. Draw cards and answer questions\n"
        "4. Discuss your answers together\n\n"
        "**Commands:**\n"
        "• /start - Start a new game\n"
        "• /help - Show this help\n"
        "• /reset - Reset current game\n\n"
        "Enjoy your intimate conversations! 💕"
    )

    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /reset command."""
    if not update.message:
        return

    reset_text = (
        "🔄 Reset Game\n\n"
        "Are you sure you want to reset your current game? "
        "This will clear your progress and start over."
    )

    await update.message.reply_text(
        reset_text,
        reply_markup=get_reset_confirmation_keyboard()
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    if not query or not query.message or not query.message.chat:
        logger.warning("Callback query received but missing query, message, or chat")
        return

    chat_id = query.message.chat.id
    logger.info(f"Callback query received: {query.data} from chat {chat_id}")

    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")

    session = get_session(chat_id)
    data = query.data

    if not data:
        logger.warning("Callback query received with no data")
        return

    try:
        if data == "back_to_themes":
            await show_theme_selection(query)
        elif data.startswith("theme_"):
            await handle_theme_selection(query, data)
        elif data.startswith("level_"):
            await handle_level_selection(query, data, session)
        elif data.startswith("content_"):
            await handle_content_type_selection(query, data, session)
        elif data == "nsfw_confirm":
            await handle_nsfw_confirmation(query, session)
        elif data == "nsfw_deny":
            await handle_nsfw_denial(query)
        elif data == "draw_card":
            await handle_draw_card(query, session)
        elif data == "toggle_content":
            await handle_toggle_content(query, session)
        elif data == "reset_game":
            await handle_reset_request(query)
        elif data == "reset_confirm":
            await handle_reset_confirmation(query, session)
        elif data == "reset_cancel":
            await handle_reset_cancel(query)
        elif data == "back_to_levels":
            await handle_back_to_levels(query, session)
        else:
            logger.warning(f"Unknown callback data: {data}")
    except Exception as e:
        logger.error(f"Error handling callback query {data}: {e}")
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except Exception as edit_error:
            logger.error(f"Error editing message: {edit_error}")


async def show_theme_selection(query: Any) -> None:
    """Show theme selection menu."""
    welcome_text = (
        "🎴 Choose a theme to begin your journey:"
    )

    await query.edit_message_text(
        welcome_text,
        reply_markup=get_theme_keyboard()
    )


async def handle_theme_selection(query: Any, data: str) -> None:
    """Handle theme selection."""
    theme_name = data.replace("theme_", "")
    try:
        theme = Theme(theme_name)
    except ValueError:
        await query.edit_message_text("❌ Invalid theme selected.")
        return

    chat_id = query.message.chat.id
    session = get_session(chat_id)
    session.theme = theme

    available_levels = GAME_DATA.get_available_levels(theme)

    if not available_levels:
        await query.edit_message_text("❌ No levels available for this theme.")
        return

    # Check if NSFW confirmation is needed
    if GAME_DATA.has_nsfw_content(theme) and not session.is_nsfw_confirmed:
        nsfw_text = (
            "⚠️ NSFW Content Warning\n\n"
            "The Sex theme contains adult content including explicit questions and tasks. "
            "You must be 18 or older to access this content.\n\n"
            "Are you 18 or older?"
        )

        await query.edit_message_text(
            nsfw_text,
            reply_markup=get_nsfw_confirmation_keyboard()
        )
        return

    await show_level_selection(query, theme, available_levels)


async def show_level_selection(query: Any, theme: Theme, available_levels: list[int]) -> None:
    """Show level selection menu."""
    theme_emojis = {
        Theme.ACQUAINTANCE: "🤝",
        Theme.FOR_COUPLES: "💕",
        Theme.SEX: "🔥",
        Theme.PROVOCATION: "⚡",
    }

    emoji = theme_emojis.get(theme, "🎴")
    level_text = f"{emoji} {theme.value}\n\nSelect a level:"

    await query.edit_message_text(
        level_text,
        reply_markup=get_level_keyboard(theme, available_levels)
    )


async def handle_level_selection(query: Any, data: str, session: SessionState) -> None:
    """Handle level selection."""
    level = int(data.replace("level_", ""))
    session.level = level

    # Check if content type selection is needed (Sex theme)
    if not session.theme:
        await query.edit_message_text("❌ No theme selected.")
        return

    available_types = GAME_DATA.get_available_content_types(session.theme, level)

    if len(available_types) > 1:
        # Multiple content types available, show selection
        content_text = (
            f"🔥 {session.theme.value} - Level {level}\n\n"
            "Choose content type:"
        )

        await query.edit_message_text(
            content_text,
            reply_markup=get_content_type_keyboard(available_types)
        )
    else:
        # Only one content type, start game
        session.content_type = available_types[0]
        await start_game(query, session)


async def handle_content_type_selection(query: Any, data: str, session: SessionState) -> None:
    """Handle content type selection."""
    content_type_str = data.replace("content_", "")
    try:
        content_type = ContentType(content_type_str)
    except ValueError:
        await query.edit_message_text("❌ Invalid content type selected.")
        return

    session.content_type = content_type
    await start_game(query, session)


async def handle_nsfw_confirmation(query: Any, session: SessionState) -> None:
    """Handle NSFW content confirmation."""
    session.is_nsfw_confirmed = True

    if not session.theme:
        await query.edit_message_text("❌ No theme selected.")
        return

    available_levels = GAME_DATA.get_available_levels(session.theme)
    await show_level_selection(query, session.theme, available_levels)


async def handle_nsfw_denial(query: Any) -> None:
    """Handle NSFW content denial."""
    denial_text = (
        "❌ Access Denied\n\n"
        "You must be 18 or older to access NSFW content. "
        "Please choose a different theme."
    )

    await query.edit_message_text(
        denial_text,
        reply_markup=get_theme_keyboard()
    )


async def start_game(query: Any, session: SessionState) -> None:
    """Start the game with current session settings."""
    if not session.theme or not session.level:
        await query.edit_message_text("❌ Invalid session state.")
        return

    remaining_cards = get_remaining_cards_count(session, GAME_DATA)

    game_text = (
        f"🎴 {session.theme.value} - Level {session.level}\n"
        f"📋 {session.content_type.value.title()}\n\n"
        f"Cards remaining: {remaining_cards}\n\n"
        "Ready to draw your first card?"
    )

    await query.edit_message_text(
        game_text,
        reply_markup=get_game_keyboard(remaining_cards)
    )


async def handle_draw_card(query: Any, session: SessionState) -> None:
    """Handle drawing a card."""
    if not can_draw_card(session, GAME_DATA):
        await query.edit_message_text(
            "🎉 Congratulations! You've completed all cards in this level.\n\n"
            "Would you like to start a new game?",
            reply_markup=get_theme_keyboard()
        )
        return

    card = draw_card(session, GAME_DATA)
    if not card:
        await query.edit_message_text("❌ No cards available.")
        return

    remaining_cards = get_remaining_cards_count(session, GAME_DATA)

    card_text = (
        f"🎴 **{session.content_type.value.title()}**\n\n"
        f"{card}\n\n"
        f"Cards remaining: {remaining_cards}"
    )

    await query.edit_message_text(
        card_text,
        reply_markup=get_game_keyboard(remaining_cards),
        parse_mode="Markdown"
    )


async def handle_toggle_content(query: Any, session: SessionState) -> None:
    """Handle toggling between questions and tasks."""
    if not session.theme or not session.level:
        await query.edit_message_text("❌ No active game session.")
        return

    available_types = GAME_DATA.get_available_content_types(session.theme, session.level)

    if len(available_types) <= 1:
        await query.edit_message_text(
            "❌ Only one content type available for this level.",
            reply_markup=get_game_keyboard(get_remaining_cards_count(session, GAME_DATA))
        )
        return

    # Toggle content type
    current_index = available_types.index(session.content_type)
    next_index = (current_index + 1) % len(available_types)
    session.content_type = available_types[next_index]

    # Reset drawn cards for new content type
    session.drawn_cards.clear()

    remaining_cards = get_remaining_cards_count(session, GAME_DATA)

    toggle_text = (
        f"🔄 Switched to {session.content_type.value.title()}\n\n"
        f"Cards remaining: {remaining_cards}\n\n"
        "Ready to draw your first card?"
    )

    await query.edit_message_text(
        toggle_text,
        reply_markup=get_game_keyboard(remaining_cards)
    )


async def handle_reset_request(query: Any) -> None:
    """Handle reset game request."""
    reset_text = (
        "🔄 Reset Game\n\n"
        "Are you sure you want to reset your current game? "
        "This will clear your progress and start over."
    )

    await query.edit_message_text(
        reset_text,
        reply_markup=get_reset_confirmation_keyboard()
    )


async def handle_reset_confirmation(query: Any, session: SessionState) -> None:
    """Handle reset confirmation."""
    reset_session(query.message.chat.id)

    reset_text = (
        "🔄 Game Reset\n\n"
        "Your game has been reset. Choose a theme to start a new game:"
    )

    await query.edit_message_text(
        reset_text,
        reply_markup=get_theme_keyboard()
    )


async def handle_reset_cancel(query: Any) -> None:
    """Handle reset cancellation."""
    chat_id = query.message.chat.id
    session = get_session(chat_id)
    remaining_cards = get_remaining_cards_count(session, GAME_DATA)

    cancel_text = (
        "❌ Reset cancelled.\n\n"
        "Your game continues as before."
    )

    await query.edit_message_text(
        cancel_text,
        reply_markup=get_game_keyboard(remaining_cards)
    )


async def handle_back_to_levels(query: Any, session: SessionState) -> None:
    """Handle going back to level selection."""
    if not session.theme:
        await show_theme_selection(query)
        return

    available_levels = GAME_DATA.get_available_levels(session.theme)
    await show_level_selection(query, session.theme, available_levels)
