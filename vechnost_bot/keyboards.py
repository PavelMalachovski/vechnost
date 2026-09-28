"""Inline keyboards for the Vechnost bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import Language, get_text
from .models import Theme


def get_theme_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for theme selection."""
    keyboard = [
        [
            InlineKeyboardButton(
                get_text("themes.Acquaintance", language), callback_data="theme_Acquaintance"
            )
        ],
        [
            InlineKeyboardButton(
                get_text("themes.For Couples", language), callback_data="theme_For Couples"
            )
        ],
        [InlineKeyboardButton(get_text("themes.Sex", language), callback_data="theme_Sex")],
        [
            InlineKeyboardButton(
                get_text("themes.Provocation", language), callback_data="theme_Provocation"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_level_keyboard(
    theme: Theme, available_levels: list[int], language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for level selection."""
    keyboard = []

    for level in available_levels:
        button_text = f"{get_text('level.level', language)} {level}"
        if theme == Theme.SEX:
            button_text = f"🔥 {button_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"level_{level}")])

    # Add back button
    keyboard.append(
        [InlineKeyboardButton(get_text("navigation.back", language), callback_data="back:themes")]
    )

    return InlineKeyboardMarkup(keyboard)


def get_calendar_keyboard(
    topic_code: str,
    level_or_0: int,
    category: str,
    page: int,
    items: list,
    total_pages: int,
    show_toggle: bool = False,
    language: Language = Language.RUSSIAN,
) -> InlineKeyboardMarkup:
    """Get keyboard for calendar navigation."""
    keyboard = []
    items_per_page = 28
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(items))

    # The cards on this page, seven to a row. Only the cards: the grid used
    # to be padded out to 7x4 with blank buttons that did nothing, sixteen of
    # them on a short last page (audit D-33).
    for row_start in range(start_idx, end_idx, 7):
        # The category rides in the callback: sessions expire, and a card
        # recovered from a fresh default session used to serve a question
        # where a task was tapped.
        keyboard.append(
            [
                InlineKeyboardButton(
                    str(item_idx + 1),
                    callback_data=f"q:{topic_code}:{level_or_0}:{item_idx}:{category}",
                )
                for item_idx in range(row_start, min(row_start + 7, end_idx))
            ]
        )

    # Between pages. Which page this is lives in the message text
    # (`callback_handlers._calendar_text`), not in a button that does
    # nothing; and the label already carries its arrow, so none is added.
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                get_text("navigation.previous", language),
                callback_data=f"cal:{topic_code}:{level_or_0}:{category}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                get_text("navigation.next", language),
                callback_data=f"cal:{topic_code}:{level_or_0}:{category}:{page + 1}",
            )
        )
    if nav_row:
        keyboard.append(nav_row)

    # Toggle row (only for Sex theme)
    if show_toggle:
        toggle_row = []
        if category == "q":
            toggle_row.append(
                InlineKeyboardButton(
                    f"📝 {get_text('navigation.toggle_tasks', language)}",
                    callback_data="toggle:sex:0:t",
                )
            )
        else:
            toggle_row.append(
                InlineKeyboardButton(
                    f"❓ {get_text('navigation.toggle_questions', language)}",
                    callback_data="toggle:sex:0:q",
                )
            )
        keyboard.append(toggle_row)

    # Back button
    keyboard.append(
        [InlineKeyboardButton(get_text("navigation.back", language), callback_data="back:themes")]
    )

    return InlineKeyboardMarkup(keyboard)


def get_question_keyboard(
    topic_code: str,
    level_or_0: int,
    question_idx: int,
    total_questions: int,
    language: Language = Language.RUSSIAN,
    category: str = "q",
) -> InlineKeyboardMarkup:
    """Get keyboard for question navigation."""
    keyboard = []

    # Navigation row (without question number)
    nav_row = []
    if question_idx > 0:
        nav_row.append(
            InlineKeyboardButton(
                get_text("navigation.previous", language),
                callback_data=f"nav:{topic_code}:{level_or_0}:{question_idx - 1}:{category}",
            )
        )

    if question_idx < total_questions - 1:
        nav_row.append(
            InlineKeyboardButton(
                get_text("navigation.next", language),
                callback_data=f"nav:{topic_code}:{level_or_0}:{question_idx + 1}:{category}",
            )
        )

    if nav_row:
        keyboard.append(nav_row)

    # Back to the deck. The card's number used to sit beside it as a button
    # that did nothing (audit D-33); it is printed on the card itself
    # («Провокация · 4/30»), and heads the text when the image cannot be.
    keyboard.append(
        [InlineKeyboardButton(get_text("navigation.back", language), callback_data="back:calendar")]
    )

    return InlineKeyboardMarkup(keyboard)


def get_nsfw_confirmation_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for NSFW content confirmation."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {get_text('nsfw.confirm', language)}", callback_data="nsfw_confirm"
            ),
            InlineKeyboardButton(
                f"❌ {get_text('nsfw.deny', language)}", callback_data="nsfw_deny"
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reset_confirmation_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for reset confirmation."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {get_text('reset.confirm', language)}", callback_data="reset_confirm"
            ),
            InlineKeyboardButton(
                f"❌ {get_text('reset.cancel', language)}", callback_data="reset_cancel"
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
