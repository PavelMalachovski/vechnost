"""Pydantic models for callback data validation and parsing."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CallbackAction(str, Enum):
    """Available callback actions."""

    THEME = "theme"
    LEVEL = "level"
    CALENDAR = "cal"
    QUESTION = "q"
    NAVIGATION = "nav"
    TOGGLE = "toggle"
    BACK = "back"
    NSFW_CONFIRM = "nsfw_confirm"
    NSFW_DENY = "nsfw_deny"
    RESET_GAME = "reset_game"
    RESET_CONFIRM = "reset_confirm"
    RESET_CANCEL = "reset_cancel"
    NOOP = "noop"
    LANGUAGE = "lang"
    LANGUAGE_CONFIRM = "lang_confirm"
    LANGUAGE_BACK = "lang_back"
    # Payment actions
    ENTER_VECHNOST = "enter_vechnost"
    WHAT_INSIDE = "what_inside"
    WHY_HELPS = "why_helps"
    REVIEWS = "reviews"
    GUARANTEE = "guarantee"
    SUBSCRIPTION_UPGRADE = "subscription_upgrade_premium"
    SUBSCRIPTION_STATUS = "subscription_status"
    PAYMENT_PLAN_MONTHLY = "payment_plan_monthly"
    PAYMENT_PLAN_YEARLY = "payment_plan_yearly"
    PAYMENT_CHECK = "payment_check"
    PAYMENT_CANCEL = "payment_cancel"


class CallbackData(BaseModel):
    """Base model for callback data validation."""

    action: CallbackAction
    raw_data: str = Field(..., description="Original callback data string")

    @classmethod
    def parse(cls, data: str) -> "CallbackData":
        """Parse callback data string into structured data."""
        if not data or len(data) > 100:  # Reasonable limit
            raise ValueError(f"Invalid callback data: {data}")

        # Check for malicious patterns
        dangerous_patterns = ['..', '/', '\\', 'script', 'javascript']
        if any(pattern in data.lower() for pattern in dangerous_patterns):
            raise ValueError(f"Potentially malicious callback data: {data}")

        # Parse based on action prefix
        if data.startswith("theme_"):
            return ThemeCallbackData.parse(data)
        elif data.startswith("level_"):
            return LevelCallbackData.parse(data)
        elif data.startswith("cal:"):
            return CalendarCallbackData.parse(data)
        elif data.startswith("q:"):
            return QuestionCallbackData.parse(data)
        elif data.startswith("nav:"):
            return NavigationCallbackData.parse(data)
        elif data.startswith("toggle:"):
            return ToggleCallbackData.parse(data)
        elif data.startswith("back:"):
            return BackCallbackData.parse(data)
        elif data.startswith("lang_confirm_"):
            return LanguageConfirmCallbackData.parse(data)
        elif data.startswith("lang_"):
            return LanguageCallbackData.parse(data)
        elif data == "lang_back":
            return LanguageBackCallbackData.parse(data)
        elif data in ["nsfw_confirm", "nsfw_deny", "reset_game", "reset_confirm", "reset_cancel", "noop",
                      "enter_vechnost", "what_inside", "why_helps", "reviews", "guarantee",
                      "subscription_upgrade_premium", "subscription_status", "payment_plan_monthly",
                      "payment_plan_yearly", "payment_check", "payment_cancel"]:
            return SimpleCallbackData.parse(data)
        else:
            raise ValueError(f"Unknown callback action: {data}")


class ThemeCallbackData(CallbackData):
    """Callback data for theme selection."""

    action: CallbackAction = CallbackAction.THEME
    theme_name: str = Field(..., description="Theme name")

    @classmethod
    def parse(cls, data: str) -> "ThemeCallbackData":
        """Parse theme callback data."""
        if not data.startswith("theme_"):
            raise ValueError(f"Invalid theme callback data: {data}")

        theme_name = data.replace("theme_", "")
        if not theme_name:
            raise ValueError("Empty theme name")

        return cls(raw_data=data, theme_name=theme_name)


class LevelCallbackData(CallbackData):
    """Callback data for level selection."""

    action: CallbackAction = CallbackAction.LEVEL
    level: int = Field(..., description="Level number")

    @classmethod
    def parse(cls, data: str) -> "LevelCallbackData":
        """Parse level callback data."""
        if not data.startswith("level_"):
            raise ValueError(f"Invalid level callback data: {data}")

        level_str = data.replace("level_", "")
        try:
            level = int(level_str)
        except ValueError:
            raise ValueError(f"Invalid level number: {level_str}")

        if level < 1 or level > 10:  # Reasonable level range
            raise ValueError(f"Level out of range: {level}")

        return cls(raw_data=data, level=level)


class CalendarCallbackData(CallbackData):
    """Callback data for calendar navigation."""

    action: CallbackAction = CallbackAction.CALENDAR
    topic: str = Field(..., description="Topic code")
    level_or_0: int = Field(..., description="Level number or 0")
    category: str = Field(..., description="Category (q or t)")
    page: int = Field(..., description="Page number")

    @classmethod
    def parse(cls, data: str) -> "CalendarCallbackData":
        """Parse calendar callback data."""
        if not data.startswith("cal:"):
            raise ValueError(f"Invalid calendar callback data: {data}")

        parts = data.split(":")
        if len(parts) != 5:
            raise ValueError(f"Invalid calendar callback format: {data}")

        topic = parts[1]
        try:
            level_or_0 = int(parts[2])
            page = int(parts[4])
        except ValueError as e:
            raise ValueError(f"Invalid numeric values in calendar callback: {e}")

        category = parts[3]
        if category not in ["q", "t"]:
            raise ValueError(f"Invalid category: {category}")

        if level_or_0 < 0 or level_or_0 > 10:
            raise ValueError(f"Level out of range: {level_or_0}")

        if page < 0:
            raise ValueError(f"Page out of range: {page}")

        return cls(
            raw_data=data,
            topic=topic,
            level_or_0=level_or_0,
            category=category,
            page=page
        )


class QuestionCallbackData(CallbackData):
    """Callback data for question selection."""

    action: CallbackAction = CallbackAction.QUESTION
    topic: str = Field(..., description="Topic code")
    level_or_0: int = Field(..., description="Level number or 0")
    index: int = Field(..., description="Question index")

    @classmethod
    def parse(cls, data: str) -> "QuestionCallbackData":
        """Parse question callback data."""
        if not data.startswith("q:"):
            raise ValueError(f"Invalid question callback data: {data}")

        parts = data.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid question callback format: {data}")

        topic = parts[1]
        try:
            level_or_0 = int(parts[2])
            index = int(parts[3])
        except ValueError as e:
            raise ValueError(f"Invalid numeric values in question callback: {e}")

        if level_or_0 < 0 or level_or_0 > 10:
            raise ValueError(f"Level out of range: {level_or_0}")

        if index < 0:
            raise ValueError(f"Index out of range: {index}")

        return cls(
            raw_data=data,
            topic=topic,
            level_or_0=level_or_0,
            index=index
        )


class NavigationCallbackData(CallbackData):
    """Callback data for question navigation."""

    action: CallbackAction = CallbackAction.NAVIGATION
    topic: str = Field(..., description="Topic code")
    level_or_0: int = Field(..., description="Level number or 0")
    index: int = Field(..., description="Question index")

    @classmethod
    def parse(cls, data: str) -> "NavigationCallbackData":
        """Parse navigation callback data."""
        if not data.startswith("nav:"):
            raise ValueError(f"Invalid navigation callback data: {data}")

        parts = data.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid navigation callback format: {data}")

        topic = parts[1]
        try:
            level_or_0 = int(parts[2])
            index = int(parts[3])
        except ValueError as e:
            raise ValueError(f"Invalid numeric values in navigation callback: {e}")

        if level_or_0 < 0 or level_or_0 > 10:
            raise ValueError(f"Level out of range: {level_or_0}")

        if index < 0:
            raise ValueError(f"Index out of range: {index}")

        return cls(
            raw_data=data,
            topic=topic,
            level_or_0=level_or_0,
            index=index
        )


class ToggleCallbackData(CallbackData):
    """Callback data for content type toggle."""

    action: CallbackAction = CallbackAction.TOGGLE
    topic: str = Field(..., description="Topic code")
    category: str = Field(..., description="Category (q or t)")
    page: int = Field(..., description="Page number")

    @classmethod
    def parse(cls, data: str) -> "ToggleCallbackData":
        """Parse toggle callback data."""
        if not data.startswith("toggle:"):
            raise ValueError(f"Invalid toggle callback data: {data}")

        parts = data.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid toggle callback format: {data}")

        topic = parts[1]
        page = int(parts[2])
        category = parts[3]

        if category not in ["q", "t"]:
            raise ValueError(f"Invalid category: {category}")

        if page < 0:
            raise ValueError(f"Page out of range: {page}")

        return cls(
            raw_data=data,
            topic=topic,
            category=category,
            page=page
        )


class BackCallbackData(CallbackData):
    """Callback data for back navigation."""

    action: CallbackAction = CallbackAction.BACK
    destination: str = Field(..., description="Back destination")

    @classmethod
    def parse(cls, data: str) -> "BackCallbackData":
        """Parse back callback data."""
        if not data.startswith("back:"):
            raise ValueError(f"Invalid back callback data: {data}")

        parts = data.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid back callback format: {data}")

        destination = parts[1]
        if not destination:
            raise ValueError("Empty back destination")

        return cls(raw_data=data, destination=destination)


class SimpleCallbackData(CallbackData):
    """Callback data for simple actions."""

    action: CallbackAction = Field(..., description="Action type")

    @classmethod
    def parse(cls, data: str) -> "SimpleCallbackData":
        """Parse simple callback data."""
        try:
            action = CallbackAction(data)
        except ValueError:
            raise ValueError(f"Unknown simple action: {data}")

        return cls(raw_data=data, action=action)


class LanguageCallbackData(CallbackData):
    """Callback data for language selection."""

    action: CallbackAction = CallbackAction.LANGUAGE
    language_code: str

    @classmethod
    def parse(cls, data: str) -> "LanguageCallbackData":
        """Parse language callback data."""
        if not data.startswith("lang_"):
            raise ValueError(f"Invalid language callback data: {data}")

        language_code = data[5:]  # Remove "lang_" prefix
        if not language_code:
            raise ValueError("Empty language code")

        return cls(raw_data=data, language_code=language_code)


class LanguageConfirmCallbackData(CallbackData):
    """Callback data for language confirmation."""

    action: CallbackAction = CallbackAction.LANGUAGE_CONFIRM
    language_code: str

    @classmethod
    def parse(cls, data: str) -> "LanguageConfirmCallbackData":
        """Parse language confirmation callback data."""
        if not data.startswith("lang_confirm_"):
            raise ValueError(f"Invalid language confirmation callback data: {data}")

        language_code = data[13:]  # Remove "lang_confirm_" prefix
        if not language_code:
            raise ValueError("Empty language code")

        return cls(raw_data=data, language_code=language_code)


class LanguageBackCallbackData(CallbackData):
    """Callback data for language selection back navigation."""

    action: CallbackAction = CallbackAction.LANGUAGE_BACK

    @classmethod
    def parse(cls, data: str) -> "LanguageBackCallbackData":
        """Parse language back callback data."""
        if data != "lang_back":
            raise ValueError(f"Invalid language back callback data: {data}")

        return cls(raw_data=data)
