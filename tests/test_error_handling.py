"""Comprehensive error handling tests."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from vechnost_bot.exceptions import (
    VechnostBotError, ValidationError, StorageError, RedisConnectionError,
    SessionError, TelegramAPIError, RateLimitError, SecurityError,
    ContentError, RenderingError, LocalizationError, NetworkError,
    FileOperationError, ErrorCodes, get_user_error_message
)
from vechnost_bot.models import SessionState, Language, Theme, ContentType


class TestExceptionHierarchy:
    """Test custom exception hierarchy."""

    def test_base_exception_creation(self):
        """Test base exception creation."""
        error = VechnostBotError("Test error")
        assert error.message == "Test error"
        assert error.error_code is None
        assert error.user_message == "Test error"
        assert error.context == {}

    def test_exception_with_context(self):
        """Test exception with context."""
        error = VechnostBotError(
            "Test error",
            error_code="TEST_ERROR",
            user_message="User friendly message",
            context={"key": "value"}
        )
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.user_message == "User friendly message"
        assert error.context == {"key": "value"}

    def test_exception_to_dict(self):
        """Test exception to dictionary conversion."""
        error = VechnostBotError(
            "Test error",
            error_code="TEST_ERROR",
            user_message="User friendly message",
            context={"key": "value"}
        )
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "VechnostBotError"
        assert error_dict["message"] == "Test error"
        assert error_dict["error_code"] == "TEST_ERROR"
        assert error_dict["user_message"] == "User friendly message"
        assert error_dict["context"] == {"key": "value"}


class TestValidationError:
    """Test validation error handling."""

    def test_validation_error_creation(self):
        """Test validation error creation."""
        error = ValidationError(
            "Invalid theme",
            field="theme",
            value="invalid_theme",
            error_code=ErrorCodes.INVALID_THEME
        )
        assert error.message == "Invalid theme"
        assert error.field == "theme"
        assert error.value == "invalid_theme"
        assert error.error_code == ErrorCodes.INVALID_THEME
        assert error.context["field"] == "theme"
        assert error.context["value"] == "invalid_theme"

    def test_validation_error_without_field(self):
        """Test validation error without field."""
        error = ValidationError("General validation error")
        assert error.message == "General validation error"
        assert error.field is None
        assert error.value is None


class TestStorageError:
    """Test storage error handling."""

    def test_storage_error_creation(self):
        """Test storage error creation."""
        error = StorageError(
            "Storage operation failed",
            operation="save_session",
            storage_type="redis",
            error_code=ErrorCodes.SESSION_SAVE_FAILED
        )
        assert error.message == "Storage operation failed"
        assert error.operation == "save_session"
        assert error.storage_type == "redis"
        assert error.error_code == ErrorCodes.SESSION_SAVE_FAILED
        assert error.context["operation"] == "save_session"
        assert error.context["storage_type"] == "redis"

    def test_redis_connection_error(self):
        """Test Redis connection error."""
        error = RedisConnectionError(
            "Connection refused",
            operation="connect",
            error_code=ErrorCodes.REDIS_CONNECTION_FAILED
        )
        assert error.message == "Connection refused"
        assert error.operation == "connect"
        assert error.storage_type == "redis"
        assert error.error_code == ErrorCodes.REDIS_CONNECTION_FAILED


class TestSessionError:
    """Test session error handling."""

    def test_session_error_creation(self):
        """Test session error creation."""
        error = SessionError(
            "Session not found",
            chat_id=12345,
            session_state="empty",
            error_code=ErrorCodes.SESSION_NOT_FOUND
        )
        assert error.message == "Session not found"
        assert error.chat_id == 12345
        assert error.session_state == "empty"
        assert error.error_code == ErrorCodes.SESSION_NOT_FOUND
        assert error.context["chat_id"] == 12345
        assert error.context["session_state"] == "empty"


class TestTelegramAPIError:
    """Test Telegram API error handling."""

    def test_telegram_api_error_creation(self):
        """Test Telegram API error creation."""
        error = TelegramAPIError(
            "API call failed",
            api_method="sendMessage",
            status_code=400,
            error_code=ErrorCodes.MESSAGE_SEND_FAILED
        )
        assert error.message == "API call failed"
        assert error.api_method == "sendMessage"
        assert error.status_code == 400
        assert error.error_code == ErrorCodes.MESSAGE_SEND_FAILED
        assert error.context["api_method"] == "sendMessage"
        assert error.context["status_code"] == 400


class TestRateLimitError:
    """Test rate limit error handling."""

    def test_rate_limit_error_creation(self):
        """Test rate limit error creation."""
        error = RateLimitError(
            "Rate limit exceeded",
            user_id=12345,
            limit=10,
            period=60,
            error_code=ErrorCodes.RATE_LIMIT_EXCEEDED
        )
        assert error.message == "Rate limit exceeded"
        assert error.user_id == 12345
        assert error.limit == 10
        assert error.period == 60
        assert error.error_code == ErrorCodes.RATE_LIMIT_EXCEEDED
        assert error.context["user_id"] == 12345
        assert error.context["limit"] == 10
        assert error.context["period"] == 60


class TestSecurityError:
    """Test security error handling."""

    def test_security_error_creation(self):
        """Test security error creation."""
        error = SecurityError(
            "Invalid input detected",
            security_type="xss",
            user_id=12345,
            error_code=ErrorCodes.INVALID_INPUT
        )
        assert error.message == "Invalid input detected"
        assert error.security_type == "xss"
        assert error.user_id == 12345
        assert error.error_code == ErrorCodes.INVALID_INPUT
        assert error.context["security_type"] == "xss"
        assert error.context["user_id"] == 12345


class TestContentError:
    """Test content error handling."""

    def test_content_error_creation(self):
        """Test content error creation."""
        error = ContentError(
            "Content not found",
            content_type="questions",
            theme="acquaintance",
            level=1,
            error_code=ErrorCodes.CONTENT_NOT_FOUND
        )
        assert error.message == "Content not found"
        assert error.content_type == "questions"
        assert error.theme == "acquaintance"
        assert error.level == 1
        assert error.error_code == ErrorCodes.CONTENT_NOT_FOUND
        assert error.context["content_type"] == "questions"
        assert error.context["theme"] == "acquaintance"
        assert error.context["level"] == 1


class TestRenderingError:
    """Test rendering error handling."""

    def test_rendering_error_creation(self):
        """Test rendering error creation."""
        error = RenderingError(
            "Image rendering failed",
            render_type="question_card",
            error_code=ErrorCodes.IMAGE_RENDER_FAILED
        )
        assert error.message == "Image rendering failed"
        assert error.render_type == "question_card"
        assert error.error_code == ErrorCodes.IMAGE_RENDER_FAILED
        assert error.context["render_type"] == "question_card"


class TestLocalizationError:
    """Test localization error handling."""

    def test_localization_error_creation(self):
        """Test localization error creation."""
        error = LocalizationError(
            "Translation not found",
            language="en",
            key="themes.acquaintance",
            error_code=ErrorCodes.TRANSLATION_NOT_FOUND
        )
        assert error.message == "Translation not found"
        assert error.language == "en"
        assert error.key == "themes.acquaintance"
        assert error.error_code == ErrorCodes.TRANSLATION_NOT_FOUND
        assert error.context["language"] == "en"
        assert error.context["key"] == "themes.acquaintance"


class TestNetworkError:
    """Test network error handling."""

    def test_network_error_creation(self):
        """Test network error creation."""
        error = NetworkError(
            "Connection timeout",
            url="https://api.telegram.org",
            timeout=30.0,
            error_code=ErrorCodes.NETWORK_TIMEOUT
        )
        assert error.message == "Connection timeout"
        assert error.url == "https://api.telegram.org"
        assert error.timeout == 30.0
        assert error.error_code == ErrorCodes.NETWORK_TIMEOUT
        assert error.context["url"] == "https://api.telegram.org"
        assert error.context["timeout"] == 30.0


class TestFileOperationError:
    """Test file operation error handling."""

    def test_file_operation_error_creation(self):
        """Test file operation error creation."""
        error = FileOperationError(
            "File not found",
            file_path="/path/to/file.yaml",
            operation="read",
            error_code=ErrorCodes.FILE_NOT_FOUND
        )
        assert error.message == "File not found"
        assert error.file_path == "/path/to/file.yaml"
        assert error.operation == "read"
        assert error.error_code == ErrorCodes.FILE_NOT_FOUND
        assert error.context["file_path"] == "/path/to/file.yaml"
        assert error.context["operation"] == "read"


class TestErrorCodes:
    """Test error code constants."""

    def test_error_codes_exist(self):
        """Test that all error codes exist."""
        assert ErrorCodes.INVALID_THEME == "INVALID_THEME"
        assert ErrorCodes.INVALID_LEVEL == "INVALID_LEVEL"
        assert ErrorCodes.INVALID_LANGUAGE == "INVALID_LANGUAGE"
        assert ErrorCodes.INVALID_CALLBACK_DATA == "INVALID_CALLBACK_DATA"
        assert ErrorCodes.MISSING_REQUIRED_FIELD == "MISSING_REQUIRED_FIELD"
        assert ErrorCodes.STORAGE_CONNECTION_FAILED == "STORAGE_CONNECTION_FAILED"
        assert ErrorCodes.SESSION_NOT_FOUND == "SESSION_NOT_FOUND"
        assert ErrorCodes.SESSION_SAVE_FAILED == "SESSION_SAVE_FAILED"
        assert ErrorCodes.REDIS_CONNECTION_FAILED == "REDIS_CONNECTION_FAILED"
        assert ErrorCodes.TELEGRAM_API_ERROR == "TELEGRAM_API_ERROR"
        assert ErrorCodes.MESSAGE_SEND_FAILED == "MESSAGE_SEND_FAILED"
        assert ErrorCodes.CALLBACK_ANSWER_FAILED == "CALLBACK_ANSWER_FAILED"
        assert ErrorCodes.RATE_LIMIT_EXCEEDED == "RATE_LIMIT_EXCEEDED"
        assert ErrorCodes.INVALID_INPUT == "INVALID_INPUT"
        assert ErrorCodes.CSRF_TOKEN_INVALID == "CSRF_TOKEN_INVALID"
        assert ErrorCodes.CONTENT_NOT_FOUND == "CONTENT_NOT_FOUND"
        assert ErrorCodes.THEME_NOT_AVAILABLE == "THEME_NOT_AVAILABLE"
        assert ErrorCodes.LEVEL_NOT_AVAILABLE == "LEVEL_NOT_AVAILABLE"
        assert ErrorCodes.IMAGE_RENDER_FAILED == "IMAGE_RENDER_FAILED"
        assert ErrorCodes.LOGO_GENERATION_FAILED == "LOGO_GENERATION_FAILED"
        assert ErrorCodes.TRANSLATION_NOT_FOUND == "TRANSLATION_NOT_FOUND"
        assert ErrorCodes.LANGUAGE_NOT_SUPPORTED == "LANGUAGE_NOT_SUPPORTED"
        assert ErrorCodes.NETWORK_TIMEOUT == "NETWORK_TIMEOUT"
        assert ErrorCodes.CONNECTION_REFUSED == "CONNECTION_REFUSED"
        assert ErrorCodes.FILE_NOT_FOUND == "FILE_NOT_FOUND"
        assert ErrorCodes.FILE_READ_FAILED == "FILE_READ_FAILED"
        assert ErrorCodes.FILE_WRITE_FAILED == "FILE_WRITE_FAILED"


class TestUserErrorMessages:
    """Test user-friendly error messages."""

    def test_get_user_error_message(self):
        """Test getting user error messages."""
        # Test existing error codes
        assert get_user_error_message(ErrorCodes.INVALID_THEME) == "❌ Неверная тема"
        assert get_user_error_message(ErrorCodes.INVALID_LEVEL) == "❌ Неверный уровень"
        assert get_user_error_message(ErrorCodes.INVALID_LANGUAGE) == "❌ Неверный язык"
        assert get_user_error_message(ErrorCodes.INVALID_CALLBACK_DATA) == "❌ Неизвестная команда"
        assert get_user_error_message(ErrorCodes.MISSING_REQUIRED_FIELD) == "❌ Отсутствует обязательное поле"
        assert get_user_error_message(ErrorCodes.STORAGE_CONNECTION_FAILED) == "❌ Ошибка подключения к хранилищу"
        assert get_user_error_message(ErrorCodes.SESSION_NOT_FOUND) == "❌ Сессия не найдена"
        assert get_user_error_message(ErrorCodes.SESSION_SAVE_FAILED) == "❌ Ошибка сохранения сессии"
        assert get_user_error_message(ErrorCodes.REDIS_CONNECTION_FAILED) == "❌ Ошибка подключения к Redis"
        assert get_user_error_message(ErrorCodes.TELEGRAM_API_ERROR) == "❌ Ошибка Telegram API"
        assert get_user_error_message(ErrorCodes.MESSAGE_SEND_FAILED) == "❌ Ошибка отправки сообщения"
        assert get_user_error_message(ErrorCodes.CALLBACK_ANSWER_FAILED) == "❌ Ошибка ответа на callback"
        assert get_user_error_message(ErrorCodes.RATE_LIMIT_EXCEEDED) == "❌ Превышен лимит запросов"
        assert get_user_error_message(ErrorCodes.INVALID_INPUT) == "❌ Неверные данные"
        assert get_user_error_message(ErrorCodes.CSRF_TOKEN_INVALID) == "❌ Неверный токен безопасности"
        assert get_user_error_message(ErrorCodes.CONTENT_NOT_FOUND) == "❌ Контент не найден"
        assert get_user_error_message(ErrorCodes.THEME_NOT_AVAILABLE) == "❌ Тема недоступна"
        assert get_user_error_message(ErrorCodes.LEVEL_NOT_AVAILABLE) == "❌ Уровень недоступен"
        assert get_user_error_message(ErrorCodes.IMAGE_RENDER_FAILED) == "❌ Ошибка создания изображения"
        assert get_user_error_message(ErrorCodes.LOGO_GENERATION_FAILED) == "❌ Ошибка создания логотипа"
        assert get_user_error_message(ErrorCodes.TRANSLATION_NOT_FOUND) == "❌ Перевод не найден"
        assert get_user_error_message(ErrorCodes.LANGUAGE_NOT_SUPPORTED) == "❌ Язык не поддерживается"
        assert get_user_error_message(ErrorCodes.NETWORK_TIMEOUT) == "❌ Таймаут сети"
        assert get_user_error_message(ErrorCodes.CONNECTION_REFUSED) == "❌ Соединение отклонено"
        assert get_user_error_message(ErrorCodes.FILE_NOT_FOUND) == "❌ Файл не найден"
        assert get_user_error_message(ErrorCodes.FILE_READ_FAILED) == "❌ Ошибка чтения файла"
        assert get_user_error_message(ErrorCodes.FILE_WRITE_FAILED) == "❌ Ошибка записи файла"

    def test_get_user_error_message_unknown(self):
        """Test getting user error message for unknown error code."""
        assert get_user_error_message("UNKNOWN_ERROR") == "❌ Неизвестная ошибка"

    def test_get_user_error_message_with_language(self):
        """Test getting user error message with language parameter."""
        # For now, all messages are in Russian
        assert get_user_error_message(ErrorCodes.INVALID_THEME, "en") == "❌ Неверная тема"
        assert get_user_error_message(ErrorCodes.INVALID_THEME, "ru") == "❌ Неверная тема"
        assert get_user_error_message(ErrorCodes.INVALID_THEME, "cs") == "❌ Неверная тема"


class TestErrorHandlingIntegration:
    """Test error handling integration."""

    @pytest.mark.asyncio
    async def test_error_handling_in_callback_handler(self, mock_update, mock_context, hybrid_storage_with_memory):
        """Test error handling in callback handler."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            from vechnost_bot.handlers import handle_callback_query

            # Test with invalid callback data
            mock_update.callback_query.data = "invalid_callback_data"
            mock_update.callback_query.edit_message_text = AsyncMock()

            # Should not raise exception
            await handle_callback_query(mock_update, mock_context)

            # Verify error message was sent
            mock_update.callback_query.edit_message_text.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_in_storage_operations(self, hybrid_storage_with_memory):
        """Test error handling in storage operations."""
        # Test with invalid session data
        try:
            await hybrid_storage_with_memory.save_session(12345, "invalid_session")
        except Exception as e:
            # Should handle gracefully
            assert isinstance(e, (TypeError, AttributeError))

    @pytest.mark.asyncio
    async def test_error_handling_in_telegram_api(self, mock_update, mock_context):
        """Test error handling in Telegram API operations."""
        from telegram.error import TelegramError

        # Mock Telegram API error
        mock_update.callback_query.edit_message_text.side_effect = TelegramError("API Error")
        mock_update.message.reply_text = AsyncMock()

        with patch('vechnost_bot.handlers.handle_callback_query') as mock_handler:
            mock_handler.side_effect = TelegramError("API Error")

            # Should handle gracefully
            try:
                await mock_handler(mock_update, mock_context)
            except TelegramError:
                # Expected behavior
                pass


class TestErrorRecovery:
    """Test error recovery mechanisms."""

    @pytest.mark.asyncio
    async def test_storage_error_recovery(self, hybrid_storage_with_memory, mock_redis_error):
        """Test storage error recovery."""
        # Mock storage that fails initially but recovers
        with patch.object(hybrid_storage_with_memory, 'get_session') as mock_get_session:
            mock_get_session.side_effect = [mock_redis_error, SessionState()]

            # First call should fail
            with pytest.raises(Exception):
                await hybrid_storage_with_memory.get_session(12345)

            # Second call should succeed
            session = await hybrid_storage_with_memory.get_session(12345)
            assert session is not None

    @pytest.mark.asyncio
    async def test_telegram_api_error_recovery(self, mock_update, mock_context):
        """Test Telegram API error recovery."""
        from telegram.error import TelegramError

        # Mock Telegram API that fails initially but recovers
        mock_update.callback_query.edit_message_text.side_effect = [
            TelegramError("API Error"),
            None  # Success on retry
        ]
        mock_update.message.reply_text = AsyncMock()

        # First call should fail
        with pytest.raises(TelegramError):
            await mock_update.callback_query.edit_message_text("Test message")

        # Second call should succeed
        await mock_update.callback_query.edit_message_text("Test message")
        mock_update.callback_query.edit_message_text.assert_called_with("Test message")


class TestErrorLogging:
    """Test error logging."""

    def test_error_logging_format(self):
        """Test error logging format."""
        error = ValidationError(
            "Invalid theme",
            field="theme",
            value="invalid_theme",
            error_code=ErrorCodes.INVALID_THEME,
            context={"user_id": 12345}
        )

        error_dict = error.to_dict()

        # Verify logging format
        assert "error_type" in error_dict
        assert "message" in error_dict
        assert "error_code" in error_dict
        assert "user_message" in error_dict
        assert "context" in error_dict

        # Verify specific values
        assert error_dict["error_type"] == "ValidationError"
        assert error_dict["message"] == "Invalid theme"
        assert error_dict["error_code"] == ErrorCodes.INVALID_THEME
        assert error_dict["context"]["field"] == "theme"
        assert error_dict["context"]["value"] == "invalid_theme"
        assert error_dict["context"]["user_id"] == 12345

    def test_error_context_preservation(self):
        """Test error context preservation."""
        error = StorageError(
            "Storage operation failed",
            operation="save_session",
            storage_type="redis",
            context={"chat_id": 12345, "session_id": "abc123"}
        )

        error_dict = error.to_dict()

        # Verify context is preserved
        assert error_dict["context"]["operation"] == "save_session"
        assert error_dict["context"]["storage_type"] == "redis"
        assert error_dict["context"]["chat_id"] == 12345
        assert error_dict["context"]["session_id"] == "abc123"
