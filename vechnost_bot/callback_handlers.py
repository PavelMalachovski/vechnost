"""Refactored callback handlers for the Vechnost bot - Complete Implementation."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from telegram import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .callback_models import (
    BackCallbackData,
    CalendarCallbackData,
    CallbackAction,
    CallbackData,
    LanguageBackCallbackData,
    LanguageCallbackData,
    LanguageConfirmCallbackData,
    LevelCallbackData,
    NavigationCallbackData,
    QuestionCallbackData,
    SimpleCallbackData,
    ThemeCallbackData,
    ToggleCallbackData,
)
from .i18n import Language, get_text, get_language_name, get_supported_languages
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


class CallbackHandler(ABC):
    """Abstract base class for callback handlers."""

    @abstractmethod
    async def handle(self, query: Any, callback_data: CallbackData, session: SessionState) -> None:
        """Handle the callback query."""
        pass


class ThemeHandler(CallbackHandler):
    """Handler for theme selection callbacks."""

    async def handle(self, query: Any, callback_data: ThemeCallbackData, session: SessionState) -> None:
        """Handle theme selection."""
        try:
            theme = Theme(callback_data.theme_name)
        except ValueError:
            await query.edit_message_text(get_text('errors.invalid_theme', session.language))
            return

        session.theme = theme

        # Check if NSFW confirmation is needed
        if GAME_DATA.has_nsfw_content(theme) and not session.is_nsfw_confirmed:
            nsfw_text = f"{get_text('nsfw.warning_title', session.language)}\n\n{get_text('nsfw.warning_text', session.language)}"
            await query.edit_message_text(
                nsfw_text,
                reply_markup=get_nsfw_confirmation_keyboard(session.language)
            )
            return

        # Handle different theme types
        if theme == Theme.SEX:
            # Sex: Show calendar immediately with toggle
            session.content_type = ContentType.QUESTIONS
            await self._show_sex_calendar(query, session, 0, ContentType.QUESTIONS)
        elif theme == Theme.PROVOCATION:
            # Provocation: Show calendar immediately
            session.content_type = ContentType.QUESTIONS
            await self._show_calendar(query, session, 0, ContentType.QUESTIONS)
        else:
            # Acquaintance, For Couples: Show level selection
            available_levels = GAME_DATA.get_available_levels(theme)
            if not available_levels:
                await query.edit_message_text("❌ Уровни недоступны для этой темы.")
                return
            await self._show_level_selection(query, theme, available_levels)

    async def _show_level_selection(self, query: Any, theme: Theme, available_levels: list[int]) -> None:
        """Show level selection menu."""
        theme_names = {
            Theme.ACQUAINTANCE: TOPIC_ACQUAINTANCE,
            Theme.FOR_COUPLES: TOPIC_FOR_COUPLES,
            Theme.SEX: TOPIC_SEX,
            Theme.PROVOCATION: TOPIC_PROVOCATION,
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

        await self._edit_or_send_message(
            query, level_text, get_level_keyboard(theme, available_levels)
        )

    async def _show_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show calendar for questions/tasks."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _show_sex_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show Sex calendar with toggle."""
        await self._show_calendar(query, session, page, content_type)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class LevelHandler(CallbackHandler):
    """Handler for level selection callbacks."""

    async def handle(self, query: Any, callback_data: LevelCallbackData, session: SessionState) -> None:
        """Handle level selection."""
        session.level = callback_data.level

        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
            return

        # Set content type and show calendar for the selected level
        session.content_type = ContentType.QUESTIONS
        await self._show_calendar(query, session, 0, ContentType.QUESTIONS)

    async def _show_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show calendar for questions/tasks."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class CalendarHandler(CallbackHandler):
    """Handler for calendar navigation callbacks."""

    async def handle(self, query: Any, callback_data: CalendarCallbackData, session: SessionState) -> None:
        """Handle calendar page navigation."""
        # Convert topic code to theme
        topic_to_theme = {
            "acq": Theme.ACQUAINTANCE,
            "couples": Theme.FOR_COUPLES,
            "sex": Theme.SEX,
            "prov": Theme.PROVOCATION
        }

        theme = topic_to_theme.get(callback_data.topic)
        if not theme:
            await query.edit_message_text(get_text('errors.invalid_theme', session.language))
            return

        # Set session state
        session.theme = theme
        session.level = callback_data.level_or_0 if callback_data.level_or_0 > 0 else None

        # Convert category to content type
        content_type = ContentType.QUESTIONS if callback_data.category == "q" else ContentType.TASKS
        session.content_type = content_type

        # Show calendar
        await self._show_calendar(query, session, callback_data.page, content_type)

    async def _show_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show calendar for questions/tasks."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class QuestionHandler(CallbackHandler):
    """Handler for question selection callbacks."""

    async def handle(self, query: Any, callback_data: QuestionCallbackData, session: SessionState) -> None:
        """Handle question selection from calendar."""
        # Convert topic code to theme
        topic_to_theme = {
            "acq": Theme.ACQUAINTANCE,
            "couples": Theme.FOR_COUPLES,
            "sex": Theme.SEX,
            "prov": Theme.PROVOCATION
        }

        theme = topic_to_theme.get(callback_data.topic)
        if not theme:
            await query.edit_message_text(get_text('errors.invalid_theme', session.language))
            return

        # Set session state
        session.theme = theme
        session.level = callback_data.level_or_0 if callback_data.level_or_0 > 0 else None

        # Get content type from current session or default to questions
        content_type = session.content_type

        # Get items
        items = GAME_DATA.get_content(theme, session.level, content_type)
        if not items or callback_data.index >= len(items):
            await query.edit_message_text("❌ Вопрос недоступен.")
            return

        # Get the question
        question = items[callback_data.index]

        # Build header
        header = get_text('question.header', session.language).format(current=callback_data.index+1, total=len(items))

        # Show question with navigation
        keyboard = get_question_keyboard(
            callback_data.topic, callback_data.level_or_0, callback_data.index, len(items)
        )

        # Try to render as image, fallback to text if it fails
        try:
            # Get background path
            bg_path = get_background_path(
                callback_data.topic, callback_data.level_or_0,
                "q" if content_type == ContentType.QUESTIONS else "t"
            )
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


class NavigationHandler(CallbackHandler):
    """Handler for question navigation callbacks."""

    async def handle(self, query: Any, callback_data: NavigationCallbackData, session: SessionState) -> None:
        """Handle navigation between questions."""
        # Convert topic code to theme
        topic_to_theme = {
            "acq": Theme.ACQUAINTANCE,
            "couples": Theme.FOR_COUPLES,
            "sex": Theme.SEX,
            "prov": Theme.PROVOCATION
        }

        theme = topic_to_theme.get(callback_data.topic)
        if not theme:
            await query.edit_message_text(get_text('errors.invalid_theme', session.language))
            return

        # Set session state
        session.theme = theme
        session.level = callback_data.level_or_0 if callback_data.level_or_0 > 0 else None

        # Get content type from current session or default to questions
        content_type = session.content_type

        # Get items
        items = GAME_DATA.get_content(theme, session.level, content_type)
        if not items or callback_data.index >= len(items):
            await query.edit_message_text("❌ Вопрос недоступен.")
            return

        # Get the question
        question = items[callback_data.index]

        # Build header
        header = get_text('question.header', session.language).format(current=callback_data.index+1, total=len(items))

        # Show question with navigation
        keyboard = get_question_keyboard(
            callback_data.topic, callback_data.level_or_0, callback_data.index, len(items)
        )

        # Try to render as image, fallback to text if it fails
        try:
            # Get background path
            bg_path = get_background_path(
                callback_data.topic, callback_data.level_or_0,
                "q" if content_type == ContentType.QUESTIONS else "t"
            )
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


class ToggleHandler(CallbackHandler):
    """Handler for content type toggle callbacks."""

    async def handle(self, query: Any, callback_data: ToggleCallbackData, session: SessionState) -> None:
        """Handle toggling between questions and tasks (Sex only)."""
        if callback_data.topic != "sex":
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))
            return

        # Set session state
        session.theme = Theme.SEX
        session.level = None  # Sex has no levels

        # Convert category to content type
        content_type = ContentType.QUESTIONS if callback_data.category == "q" else ContentType.TASKS
        session.content_type = content_type

        # Show calendar
        await self._show_sex_calendar(query, session, callback_data.page, content_type)

    async def _show_sex_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show Sex calendar with toggle."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class BackHandler(CallbackHandler):
    """Handler for back navigation callbacks."""

    async def handle(self, query: Any, callback_data: BackCallbackData, session: SessionState) -> None:
        """Handle back navigation."""
        destination = callback_data.destination
        logger.info(f"Back navigation to: {destination}, theme: {session.theme}, level: {session.level}")

        if destination == "themes":
            await self._show_theme_selection(query)
        elif destination == "levels":
            if not session.theme:
                await self._show_theme_selection(query)
                return
            available_levels = GAME_DATA.get_available_levels(session.theme)
            if available_levels:
                await self._show_level_selection(query, session.theme, available_levels)
            else:
                await self._show_theme_selection(query)
        elif destination == "calendar":
            # Go back to calendar - need to determine which calendar
            if not session.theme:
                await self._show_theme_selection(query)
                return

            # Determine current page (default to 0)
            current_page = 0

            if session.theme == Theme.SEX:
                # For Sex, show the current content type
                content_type = session.content_type
                await self._show_sex_calendar(query, session, current_page, content_type)
            else:
                # For other themes, show questions calendar
                await self._show_calendar(query, session, current_page, ContentType.QUESTIONS)
        else:
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))

    async def _show_theme_selection(self, query: Any) -> None:
        """Show theme selection menu."""
        welcome_text = WELCOME_PROMPT
        await self._edit_or_send_message(query, welcome_text, get_theme_keyboard())

    async def _show_level_selection(self, query: Any, theme: Theme, available_levels: list[int]) -> None:
        """Show level selection menu."""
        theme_names = {
            Theme.ACQUAINTANCE: TOPIC_ACQUAINTANCE,
            Theme.FOR_COUPLES: TOPIC_FOR_COUPLES,
            Theme.SEX: TOPIC_SEX,
            Theme.PROVOCATION: TOPIC_PROVOCATION,
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

        await self._edit_or_send_message(
            query, level_text, get_level_keyboard(theme, available_levels)
        )

    async def _show_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show calendar for questions/tasks."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _show_sex_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show Sex calendar with toggle."""
        await self._show_calendar(query, session, page, content_type)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class SimpleActionHandler(CallbackHandler):
    """Handler for simple action callbacks."""

    async def handle(self, query: Any, callback_data: SimpleCallbackData, session: SessionState) -> None:
        """Handle simple actions."""
        if callback_data.action == CallbackAction.NSFW_CONFIRM:
            await self._handle_nsfw_confirmation(query, session)
        elif callback_data.action == CallbackAction.NSFW_DENY:
            await self._handle_nsfw_denial(query, session)
        elif callback_data.action == CallbackAction.RESET_GAME:
            await self._handle_reset_request(query, session)
        elif callback_data.action == CallbackAction.RESET_CONFIRM:
            await self._handle_reset_confirmation(query, session)
        elif callback_data.action == CallbackAction.RESET_CANCEL:
            await self._handle_reset_cancel(query, session)
        elif callback_data.action == CallbackAction.NOOP:
            # No operation - do nothing
            pass
        else:
            logger.warning(f"Unknown simple action: {callback_data.action}")
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))

    async def _handle_nsfw_confirmation(self, query: Any, session: SessionState) -> None:
        """Handle NSFW content confirmation."""
        session.is_nsfw_confirmed = True

        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
            return

        # For Sex theme, show calendar immediately
        if session.theme == Theme.SEX:
            session.content_type = ContentType.QUESTIONS
            await self._show_sex_calendar(query, session, 0, ContentType.QUESTIONS)
        else:
            # For other themes, show level selection
            available_levels = GAME_DATA.get_available_levels(session.theme)
            if available_levels:
                await self._show_level_selection(query, session.theme, available_levels)
            else:
                await self._show_theme_selection(query)

    async def _handle_nsfw_denial(self, query: Any, session: SessionState) -> None:
        """Handle NSFW content denial."""
        await query.edit_message_text(
            get_text('nsfw.access_denied', session.language),
            reply_markup=get_theme_keyboard(session.language)
        )

    async def _handle_reset_request(self, query: Any, session: SessionState) -> None:
        """Handle reset game request."""
        reset_text = f"{get_text('reset.title', session.language)}\n\n{get_text('reset.confirm_text', session.language)}"
        await query.edit_message_text(
            reset_text,
            reply_markup=get_reset_confirmation_keyboard(session.language)
        )

    async def _handle_reset_confirmation(self, query: Any, session: SessionState) -> None:
        """Handle reset confirmation."""
        reset_session(query.message.chat.id)
        await query.edit_message_text(
            get_text('reset.completed', session.language),
            reply_markup=get_theme_keyboard(session.language)
        )

    async def _handle_reset_cancel(self, query: Any, session: SessionState) -> None:
        """Handle reset cancellation."""
        await query.edit_message_text(
            get_text('reset.cancelled', session.language),
            reply_markup=get_theme_keyboard(session.language)
        )

    async def _show_theme_selection(self, query: Any) -> None:
        """Show theme selection menu."""
        welcome_text = WELCOME_PROMPT
        await self._edit_or_send_message(query, welcome_text, get_theme_keyboard())

    async def _show_level_selection(self, query: Any, theme: Theme, available_levels: list[int]) -> None:
        """Show level selection menu."""
        theme_names = {
            Theme.ACQUAINTANCE: TOPIC_ACQUAINTANCE,
            Theme.FOR_COUPLES: TOPIC_FOR_COUPLES,
            Theme.SEX: TOPIC_SEX,
            Theme.PROVOCATION: TOPIC_PROVOCATION,
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

        await self._edit_or_send_message(
            query, level_text, get_level_keyboard(theme, available_levels)
        )

    async def _show_sex_calendar(self, query: Any, session: SessionState, page: int, content_type: ContentType) -> None:
        """Show Sex calendar with toggle."""
        if not session.theme:
            await query.edit_message_text(get_text('errors.no_theme', session.language))
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

        await self._edit_or_send_message(query, header, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class CallbackHandlerRegistry:
    """Registry for callback handlers."""

    def __init__(self):
        self._handlers: Dict[CallbackAction, CallbackHandler] = {
            CallbackAction.THEME: ThemeHandler(),
            CallbackAction.LEVEL: LevelHandler(),
            CallbackAction.CALENDAR: CalendarHandler(),
            CallbackAction.QUESTION: QuestionHandler(),
            CallbackAction.NAVIGATION: NavigationHandler(),
            CallbackAction.TOGGLE: ToggleHandler(),
            CallbackAction.BACK: BackHandler(),
            CallbackAction.NSFW_CONFIRM: SimpleActionHandler(),
            CallbackAction.NSFW_DENY: SimpleActionHandler(),
            CallbackAction.RESET_GAME: SimpleActionHandler(),
            CallbackAction.RESET_CONFIRM: SimpleActionHandler(),
            CallbackAction.RESET_CANCEL: SimpleActionHandler(),
            CallbackAction.NOOP: SimpleActionHandler(),
            CallbackAction.LANGUAGE: LanguageHandler(),
            CallbackAction.LANGUAGE_CONFIRM: LanguageConfirmHandler(),
            CallbackAction.LANGUAGE_BACK: LanguageBackHandler(),
        }

    async def handle_callback(self, query: Any, data: str) -> None:
        """Handle a callback query with the appropriate handler."""
        try:
            # Parse callback data
            callback_data = CallbackData.parse(data)

            # Get session
            chat_id = query.message.chat.id
            session = get_session(chat_id)

            # Get appropriate handler
            handler = self._handlers.get(callback_data.action)
            if not handler:
                logger.warning(f"No handler found for action: {callback_data.action}")
                await query.edit_message_text(get_text('errors.unknown_callback', session.language))
                return

            # Handle the callback
            await handler.handle(query, callback_data, session)

        except ValueError as e:
            logger.warning(f"Invalid callback data: {data}, error: {e}")
            # Get session for error message
            chat_id = query.message.chat.id
            session = get_session(chat_id)
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))
        except Exception as e:
            logger.error(f"Error handling callback query {data}: {e}", exc_info=True)
            try:
                await query.edit_message_text("❌ Произошла ошибка. Попробуйте снова.")
            except Exception as edit_error:
                logger.error(f"Error editing message: {edit_error}")


class LanguageHandler(CallbackHandler):
    """Handler for language selection callbacks."""

    async def handle(self, query: Any, callback_data: LanguageCallbackData, session: SessionState) -> None:
        """Handle language selection."""
        try:
            language = Language(callback_data.language_code)
        except ValueError:
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))
            return

        # Show language confirmation
        language_name = get_language_name(language, session.language)
        confirm_text = f"{get_text('language.confirm_title', session.language)}\n\n{language_name}\n\n{get_text('language.confirm_subtitle', session.language)}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"✓ {get_text('language.confirm', session.language)}",
                    callback_data=f"lang_confirm_{language.value}"
                ),
                InlineKeyboardButton(
                    f"← {get_text('navigation.back', session.language)}",
                    callback_data="lang_back"
                )
            ]
        ])

        await self._edit_or_send_message(query, confirm_text, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class LanguageConfirmHandler(CallbackHandler):
    """Handler for language confirmation callbacks."""

    async def handle(self, query: Any, callback_data: LanguageConfirmCallbackData, session: SessionState) -> None:
        """Handle language confirmation."""
        try:
            language = Language(callback_data.language_code)
        except ValueError:
            await query.edit_message_text(get_text('errors.unknown_callback', session.language))
            return

        # Update session language
        session.language = language

        # Show theme selection
        welcome_text = f"{get_text('welcome.title', language)}\n\n{get_text('welcome.subtitle', language)}\n\n{get_text('welcome.prompt', language)}"
        keyboard = get_theme_keyboard(language)

        await self._edit_or_send_message(query, welcome_text, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


class LanguageBackHandler(CallbackHandler):
    """Handler for language selection back navigation."""

    async def handle(self, query: Any, callback_data: LanguageBackCallbackData, session: SessionState) -> None:
        """Handle language selection back navigation."""
        # Show language selection again
        welcome_text = f"{get_text('welcome.title', session.language)}\n\n{get_text('welcome.subtitle', session.language)}\n\n{get_text('welcome.prompt', session.language)}"
        keyboard = get_language_selection_keyboard(session.language)

        await self._edit_or_send_message(query, welcome_text, keyboard)

    async def _edit_or_send_message(self, query: Any, text: str, keyboard: Any) -> None:
        """Edit message or send new one if editing fails."""
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as edit_error:
            logger.warning(f"Could not edit message text: {edit_error}, deleting and sending new message")
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.warning(f"Could not delete message: {delete_error}")
            await query.message.reply_text(text, reply_markup=keyboard)


# Global registry instance
callback_registry = CallbackHandlerRegistry()
