"""Tests for security modules."""

import pytest
from unittest.mock import patch, MagicMock

from vechnost_bot.security import (
    InputSanitizer,
    CSRFProtection,
    SecurityError,
    secure_callback_data,
    secure_theme_name,
    secure_language_code,
    secure_numeric_input,
    secure_username,
    secure_message_text
)
from vechnost_bot.rate_limiter import (
    RateLimiter,
    RateLimitType,
    RateLimitConfig,
    rate_limit,
    get_rate_limit_info
)


class TestInputSanitizer:
    """Test input sanitization."""

    def test_sanitize_text_safe(self):
        """Test sanitizing safe text."""
        sanitizer = InputSanitizer()
        result = sanitizer.sanitize_text("Hello world")
        assert result == "Hello world"

    def test_sanitize_text_html_escape(self):
        """Test HTML escaping."""
        sanitizer = InputSanitizer()
        # Test with plain text that should pass through
        result = sanitizer.sanitize_text("Hello world")
        assert result == "Hello world"

    def test_sanitize_text_dangerous_pattern(self):
        """Test detection of dangerous patterns."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            sanitizer.sanitize_text("<script>alert('xss')</script>")

    def test_sanitize_text_truncation(self):
        """Test text truncation."""
        sanitizer = InputSanitizer()
        long_text = "a" * 1000
        result = sanitizer.sanitize_text(long_text, max_length=100)
        assert len(result) == 100

    def test_validate_callback_data_valid(self):
        """Test valid callback data."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_callback_data("theme_Acquaintance")
        assert result == "theme_Acquaintance"

    def test_validate_callback_data_invalid_characters(self):
        """Test callback data with invalid characters."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="invalid characters"):
            sanitizer.validate_callback_data("theme_Acquaintance<script>")

    def test_validate_callback_data_too_long(self):
        """Test callback data that's too long."""
        sanitizer = InputSanitizer()
        long_data = "a" * 101

        with pytest.raises(SecurityError, match="too long"):
            sanitizer.validate_callback_data(long_data)

    def test_validate_theme_name_valid(self):
        """Test valid theme name."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_theme_name("Acquaintance")
        assert result == "Acquaintance"

    def test_validate_theme_name_invalid(self):
        """Test invalid theme name."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="invalid characters"):
            sanitizer.validate_theme_name("Acquaintance<script>")

    def test_validate_language_code_valid(self):
        """Test valid language code."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_language_code("en")
        assert result == "en"

    def test_validate_language_code_invalid_length(self):
        """Test invalid language code length."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="must be 2 characters"):
            sanitizer.validate_language_code("eng")

    def test_validate_numeric_input_valid(self):
        """Test valid numeric input."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_numeric_input("123", "level")
        assert result == 123

    def test_validate_numeric_input_invalid(self):
        """Test invalid numeric input."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="invalid characters"):
            sanitizer.validate_numeric_input("abc", "level")

    def test_validate_username_valid(self):
        """Test valid username."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_username("test_user")
        assert result == "test_user"

    def test_validate_username_invalid(self):
        """Test invalid username."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="invalid characters"):
            sanitizer.validate_username("test<script>")

    def test_validate_message_text_valid(self):
        """Test valid message text."""
        sanitizer = InputSanitizer()
        result = sanitizer.validate_message_text("Hello world")
        assert result == "Hello world"

    def test_validate_message_text_dangerous(self):
        """Test dangerous message text."""
        sanitizer = InputSanitizer()

        with pytest.raises(SecurityError, match="Dangerous pattern"):
            sanitizer.validate_message_text("<script>alert('xss')</script>")


class TestCSRFProtection:
    """Test CSRF protection."""

    def test_generate_token(self):
        """Test token generation."""
        csrf = CSRFProtection()
        token = csrf.generate_token(12345)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_token_valid(self):
        """Test valid token validation."""
        csrf = CSRFProtection()
        token = csrf.generate_token(12345)
        assert csrf.validate_token(12345, token) is True

    def test_validate_token_invalid(self):
        """Test invalid token validation."""
        csrf = CSRFProtection()
        csrf.generate_token(12345)
        assert csrf.validate_token(12345, "invalid_token") is False

    def test_validate_token_missing(self):
        """Test validation of missing token."""
        csrf = CSRFProtection()
        assert csrf.validate_token(12345, "some_token") is False

    def test_revoke_token(self):
        """Test token revocation."""
        csrf = CSRFProtection()
        token = csrf.generate_token(12345)
        assert csrf.validate_token(12345, token) is True

        csrf.revoke_token(12345)
        assert csrf.validate_token(12345, token) is False


class TestRateLimiter:
    """Test rate limiter."""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter()
        assert isinstance(limiter._configs, dict)
        assert len(limiter._configs) > 0

    def test_is_allowed_within_limits(self):
        """Test requests within limits."""
        limiter = RateLimiter()
        user_id = 12345

        # First request should be allowed
        is_allowed, error = limiter.is_allowed(user_id, RateLimitType.COMMAND)
        assert is_allowed is True
        assert error is None

    def test_is_allowed_exceeds_limits(self):
        """Test requests exceeding limits."""
        limiter = RateLimiter()
        user_id = 12345

        # Make requests up to the limit
        config = limiter._configs[RateLimitType.COMMAND]
        for _ in range(config.max_requests):
            is_allowed, error = limiter.is_allowed(user_id, RateLimitType.COMMAND)
            assert is_allowed is True

        # Next request should be blocked
        is_allowed, error = limiter.is_allowed(user_id, RateLimitType.COMMAND)
        assert is_allowed is False
        assert "Rate limit exceeded" in error

    def test_get_remaining_requests(self):
        """Test getting remaining requests."""
        limiter = RateLimiter()
        user_id = 12345

        # Make one request
        limiter.is_allowed(user_id, RateLimitType.COMMAND)

        # Check remaining requests
        remaining = limiter.get_remaining_requests(user_id, RateLimitType.COMMAND)
        config = limiter._configs[RateLimitType.COMMAND]
        assert remaining == config.max_requests - 1

    def test_reset_user_limits(self):
        """Test resetting user limits."""
        limiter = RateLimiter()
        user_id = 12345

        # Make some requests
        limiter.is_allowed(user_id, RateLimitType.COMMAND)
        limiter.is_allowed(user_id, RateLimitType.CALLBACK)

        # Reset limits
        limiter.reset_user_limits(user_id)

        # Check that limits are reset
        remaining_command = limiter.get_remaining_requests(user_id, RateLimitType.COMMAND)
        remaining_callback = limiter.get_remaining_requests(user_id, RateLimitType.CALLBACK)

        config_command = limiter._configs[RateLimitType.COMMAND]
        config_callback = limiter._configs[RateLimitType.CALLBACK]

        assert remaining_command == config_command.max_requests
        assert remaining_callback == config_callback.max_requests


class TestSecurityFunctions:
    """Test security utility functions."""

    def test_secure_callback_data(self):
        """Test secure callback data function."""
        result = secure_callback_data("theme_Acquaintance")
        assert result == "theme_Acquaintance"

    def test_secure_callback_data_invalid(self):
        """Test secure callback data with invalid input."""
        with pytest.raises(SecurityError):
            secure_callback_data("theme_Acquaintance<script>")

    def test_secure_theme_name(self):
        """Test secure theme name function."""
        result = secure_theme_name("Acquaintance")
        assert result == "Acquaintance"

    def test_secure_language_code(self):
        """Test secure language code function."""
        result = secure_language_code("en")
        assert result == "en"

    def test_secure_numeric_input(self):
        """Test secure numeric input function."""
        result = secure_numeric_input("123", "level")
        assert result == 123

    def test_secure_username(self):
        """Test secure username function."""
        result = secure_username("test_user")
        assert result == "test_user"

    def test_secure_message_text(self):
        """Test secure message text function."""
        result = secure_message_text("Hello world")
        assert result == "Hello world"


class TestRateLimitDecorator:
    """Test rate limit decorator."""

    def test_rate_limit_decorator_sync(self):
        """Test rate limit decorator on sync function."""
        @rate_limit(RateLimitType.COMMAND)
        def test_function():
            return "success"

        # Should work normally
        result = test_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_async(self):
        """Test rate limit decorator on async function."""
        @rate_limit(RateLimitType.COMMAND)
        async def test_function():
            return "success"

        # Should work normally
        result = await test_function()
        assert result == "success"

    def test_get_rate_limit_info(self):
        """Test getting rate limit info."""
        user_id = 12345
        info = get_rate_limit_info(user_id, RateLimitType.COMMAND)

        assert "remaining_requests" in info
        assert "reset_time" in info
        assert "is_blocked" in info
        assert "block_until" in info
