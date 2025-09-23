"""Security utilities for input sanitization and validation."""

import re
import html
from typing import Any, Optional, Union
from urllib.parse import urlparse
import structlog

logger = structlog.get_logger("security")


class SecurityError(Exception):
    """Security-related error."""
    pass


class InputSanitizer:
    """Input sanitization utilities."""

    # Dangerous patterns that should be blocked
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript protocol
        r'data:text/html',  # Data URLs with HTML
        r'vbscript:',  # VBScript protocol
        r'on\w+\s*=',  # Event handlers (onclick, onload, etc.)
        r'<iframe[^>]*>',  # Iframe tags
        r'<object[^>]*>',  # Object tags
        r'<embed[^>]*>',  # Embed tags
        r'<link[^>]*>',  # Link tags
        r'<meta[^>]*>',  # Meta tags
        r'<style[^>]*>.*?</style>',  # Style tags
        r'expression\s*\(',  # CSS expressions
        r'url\s*\(',  # CSS url() functions
        r'@import',  # CSS imports
        r'\.\./',  # Directory traversal
        r'\.\.\\',  # Directory traversal (Windows)
        r'%2e%2e%2f',  # URL encoded directory traversal
        r'%2e%2e%5c',  # URL encoded directory traversal (Windows)
        r'\\x[0-9a-fA-F]{2}',  # Hex encoded characters
        r'%[0-9a-fA-F]{2}',  # URL encoded characters
        r'<[^>]*>',  # Any HTML tags
    ]

    # Allowed characters for different input types
    ALLOWED_CHARS = {
        'callback_data': r'^[a-zA-Z0-9_:.-]+$',
        'theme_name': r'^[a-zA-Z0-9\s-]+$',
        'language_code': r'^[a-z]{2}$',
        'level': r'^[0-9]+$',
        'page': r'^[0-9]+$',
        'question_idx': r'^[0-9]+$',
    }

    # Maximum lengths for different input types
    MAX_LENGTHS = {
        'callback_data': 100,
        'theme_name': 50,
        'language_code': 2,
        'level': 3,
        'page': 10,
        'question_idx': 10,
        'username': 50,
        'message_text': 1000,
    }

    @classmethod
    def sanitize_text(cls, text: str, max_length: Optional[int] = None) -> str:
        """
        Sanitize text input by removing dangerous content.

        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text

        Raises:
            SecurityError: If input contains dangerous content
        """
        if not isinstance(text, str):
            raise SecurityError(f"Expected string input, got {type(text)}")

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                logger.warning(
                    "dangerous_pattern_detected",
                    pattern=pattern,
                    text=text[:100] + "..." if len(text) > 100 else text
                )
                raise SecurityError(f"Dangerous pattern detected: {pattern}")

        # HTML escape
        sanitized = html.escape(text)

        # Truncate if too long
        if max_length and len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
            logger.warning(
                "text_truncated",
                original_length=len(text),
                max_length=max_length
            )

        return sanitized

    @classmethod
    def validate_callback_data(cls, data: str) -> str:
        """
        Validate and sanitize callback data.

        Args:
            data: Callback data string

        Returns:
            Validated callback data

        Raises:
            SecurityError: If callback data is invalid
        """
        if not isinstance(data, str):
            raise SecurityError("Callback data must be a string")

        if len(data) > cls.MAX_LENGTHS['callback_data']:
            raise SecurityError(f"Callback data too long: {len(data)} > {cls.MAX_LENGTHS['callback_data']}")

        # Check for allowed characters
        if not re.match(cls.ALLOWED_CHARS['callback_data'], data):
            raise SecurityError(f"Callback data contains invalid characters: {data}")

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, data, re.IGNORECASE):
                raise SecurityError(f"Dangerous pattern in callback data: {pattern}")

        return data

    @classmethod
    def validate_theme_name(cls, theme: str) -> str:
        """
        Validate theme name.

        Args:
            theme: Theme name

        Returns:
            Validated theme name

        Raises:
            SecurityError: If theme name is invalid
        """
        if not isinstance(theme, str):
            raise SecurityError("Theme name must be a string")

        if len(theme) > cls.MAX_LENGTHS['theme_name']:
            raise SecurityError(f"Theme name too long: {len(theme)} > {cls.MAX_LENGTHS['theme_name']}")

        if not re.match(cls.ALLOWED_CHARS['theme_name'], theme):
            raise SecurityError(f"Theme name contains invalid characters: {theme}")

        return theme

    @classmethod
    def validate_language_code(cls, code: str) -> str:
        """
        Validate language code.

        Args:
            code: Language code

        Returns:
            Validated language code

        Raises:
            SecurityError: If language code is invalid
        """
        if not isinstance(code, str):
            raise SecurityError("Language code must be a string")

        if len(code) != cls.MAX_LENGTHS['language_code']:
            raise SecurityError(f"Language code must be {cls.MAX_LENGTHS['language_code']} characters")

        if not re.match(cls.ALLOWED_CHARS['language_code'], code):
            raise SecurityError(f"Language code contains invalid characters: {code}")

        return code.lower()

    @classmethod
    def validate_numeric_input(cls, value: Union[str, int], input_type: str) -> int:
        """
        Validate numeric input.

        Args:
            value: Numeric value to validate
            input_type: Type of input (level, page, question_idx)

        Returns:
            Validated integer value

        Raises:
            SecurityError: If input is invalid
        """
        if input_type not in cls.ALLOWED_CHARS:
            raise SecurityError(f"Unknown input type: {input_type}")

        # Convert to string for validation
        str_value = str(value)

        if len(str_value) > cls.MAX_LENGTHS.get(input_type, 10):
            raise SecurityError(f"{input_type} too long: {len(str_value)}")

        if not re.match(cls.ALLOWED_CHARS[input_type], str_value):
            raise SecurityError(f"{input_type} contains invalid characters: {str_value}")

        try:
            int_value = int(str_value)
            if int_value < 0:
                raise SecurityError(f"{input_type} must be non-negative: {int_value}")
            return int_value
        except ValueError:
            raise SecurityError(f"Invalid {input_type}: {str_value}")

    @classmethod
    def validate_username(cls, username: Optional[str]) -> Optional[str]:
        """
        Validate username.

        Args:
            username: Username to validate

        Returns:
            Validated username or None

        Raises:
            SecurityError: If username is invalid
        """
        if username is None:
            return None

        if not isinstance(username, str):
            raise SecurityError("Username must be a string")

        if len(username) > cls.MAX_LENGTHS['username']:
            raise SecurityError(f"Username too long: {len(username)} > {cls.MAX_LENGTHS['username']}")

        # Username should only contain alphanumeric characters, underscores, and hyphens
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            raise SecurityError(f"Username contains invalid characters: {username}")

        return username

    @classmethod
    def validate_message_text(cls, text: Optional[str]) -> Optional[str]:
        """
        Validate message text.

        Args:
            text: Message text to validate

        Returns:
            Validated message text or None

        Raises:
            SecurityError: If message text is invalid
        """
        if text is None:
            return None

        if not isinstance(text, str):
            raise SecurityError("Message text must be a string")

        if len(text) > cls.MAX_LENGTHS['message_text']:
            raise SecurityError(f"Message text too long: {len(text)} > {cls.MAX_LENGTHS['message_text']}")

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                raise SecurityError(f"Dangerous pattern in message text: {pattern}")

        return text


class CSRFProtection:
    """CSRF protection for callback queries."""

    def __init__(self):
        self._tokens: dict[int, str] = {}
        self._token_expiry: dict[int, float] = {}
        self._token_duration = 3600  # 1 hour

    def generate_token(self, user_id: int) -> str:
        """Generate CSRF token for user."""
        import secrets
        import time

        token = secrets.token_urlsafe(32)
        self._tokens[user_id] = token
        self._token_expiry[user_id] = time.time() + self._token_duration

        logger.debug("csrf_token_generated", user_id=user_id)
        return token

    def validate_token(self, user_id: int, token: str) -> bool:
        """Validate CSRF token for user."""
        import time

        if user_id not in self._tokens:
            logger.warning("csrf_token_missing", user_id=user_id)
            return False

        if time.time() > self._token_expiry[user_id]:
            logger.warning("csrf_token_expired", user_id=user_id)
            del self._tokens[user_id]
            del self._token_expiry[user_id]
            return False

        if self._tokens[user_id] != token:
            logger.warning("csrf_token_mismatch", user_id=user_id)
            return False

        return True

    def revoke_token(self, user_id: int) -> None:
        """Revoke CSRF token for user."""
        if user_id in self._tokens:
            del self._tokens[user_id]
        if user_id in self._token_expiry:
            del self._token_expiry[user_id]

        logger.debug("csrf_token_revoked", user_id=user_id)


# Global instances
input_sanitizer = InputSanitizer()
csrf_protection = CSRFProtection()


def secure_callback_data(data: str) -> str:
    """Secure callback data validation."""
    return input_sanitizer.validate_callback_data(data)


def secure_theme_name(theme: str) -> str:
    """Secure theme name validation."""
    return input_sanitizer.validate_theme_name(theme)


def secure_language_code(code: str) -> str:
    """Secure language code validation."""
    return input_sanitizer.validate_language_code(code)


def secure_numeric_input(value: Union[str, int], input_type: str) -> int:
    """Secure numeric input validation."""
    return input_sanitizer.validate_numeric_input(value, input_type)


def secure_username(username: Optional[str]) -> Optional[str]:
    """Secure username validation."""
    return input_sanitizer.validate_username(username)


def secure_message_text(text: Optional[str]) -> Optional[str]:
    """Secure message text validation."""
    return input_sanitizer.validate_message_text(text)
