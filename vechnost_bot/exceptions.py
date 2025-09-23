"""Custom exception hierarchy for Vechnost bot."""

from typing import Optional, Dict, Any


class VechnostBotError(Exception):
    """Base exception for Vechnost bot errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        user_message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.user_message = user_message or message
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "user_message": self.user_message,
            "context": self.context
        }


class ValidationError(VechnostBotError):
    """Data validation error."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        if field:
            self.context["field"] = field
        if value is not None:
            self.context["value"] = str(value)


class ConfigurationError(VechnostBotError):
    """Configuration error."""
    pass


class StorageError(VechnostBotError):
    """Storage operation error."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        storage_type: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.storage_type = storage_type
        if operation:
            self.context["operation"] = operation
        if storage_type:
            self.context["storage_type"] = storage_type


class RedisConnectionError(StorageError):
    """Redis connection error."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, storage_type="redis", **kwargs)


class SessionError(VechnostBotError):
    """Session management error."""

    def __init__(
        self,
        message: str,
        chat_id: Optional[int] = None,
        session_state: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.chat_id = chat_id
        self.session_state = session_state
        if chat_id:
            self.context["chat_id"] = chat_id
        if session_state:
            self.context["session_state"] = session_state


class TelegramAPIError(VechnostBotError):
    """Telegram API error."""

    def __init__(
        self,
        message: str,
        api_method: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.api_method = api_method
        self.status_code = status_code
        if api_method:
            self.context["api_method"] = api_method
        if status_code:
            self.context["status_code"] = status_code


class RateLimitError(VechnostBotError):
    """Rate limiting error."""

    def __init__(
        self,
        message: str,
        user_id: Optional[int] = None,
        limit: Optional[int] = None,
        period: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.user_id = user_id
        self.limit = limit
        self.period = period
        if user_id:
            self.context["user_id"] = user_id
        if limit:
            self.context["limit"] = limit
        if period:
            self.context["period"] = period


class SecurityError(VechnostBotError):
    """Security-related error."""

    def __init__(
        self,
        message: str,
        security_type: Optional[str] = None,
        user_id: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.security_type = security_type
        self.user_id = user_id
        if security_type:
            self.context["security_type"] = security_type
        if user_id:
            self.context["user_id"] = user_id


class ContentError(VechnostBotError):
    """Content-related error."""

    def __init__(
        self,
        message: str,
        content_type: Optional[str] = None,
        theme: Optional[str] = None,
        level: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.content_type = content_type
        self.theme = theme
        self.level = level
        if content_type:
            self.context["content_type"] = content_type
        if theme:
            self.context["theme"] = theme
        if level:
            self.context["level"] = level


class RenderingError(VechnostBotError):
    """Image rendering error."""

    def __init__(
        self,
        message: str,
        render_type: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.render_type = render_type
        if render_type:
            self.context["render_type"] = render_type


class LocalizationError(VechnostBotError):
    """Localization error."""

    def __init__(
        self,
        message: str,
        language: Optional[str] = None,
        key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.language = language
        self.key = key
        if language:
            self.context["language"] = language
        if key:
            self.context["key"] = key


class NetworkError(VechnostBotError):
    """Network-related error."""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.url = url
        self.timeout = timeout
        if url:
            self.context["url"] = url
        if timeout:
            self.context["timeout"] = timeout


class FileOperationError(VechnostBotError):
    """File operation error."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.file_path = file_path
        self.operation = operation
        if file_path:
            self.context["file_path"] = file_path
        if operation:
            self.context["operation"] = operation


# Error code constants
class ErrorCodes:
    """Error code constants."""

    # Validation errors
    INVALID_THEME = "INVALID_THEME"
    INVALID_LEVEL = "INVALID_LEVEL"
    INVALID_LANGUAGE = "INVALID_LANGUAGE"
    INVALID_CALLBACK_DATA = "INVALID_CALLBACK_DATA"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

    # Storage errors
    STORAGE_CONNECTION_FAILED = "STORAGE_CONNECTION_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_SAVE_FAILED = "SESSION_SAVE_FAILED"
    REDIS_CONNECTION_FAILED = "REDIS_CONNECTION_FAILED"

    # Telegram API errors
    TELEGRAM_API_ERROR = "TELEGRAM_API_ERROR"
    MESSAGE_SEND_FAILED = "MESSAGE_SEND_FAILED"
    CALLBACK_ANSWER_FAILED = "CALLBACK_ANSWER_FAILED"

    # Security errors
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_INPUT = "INVALID_INPUT"
    CSRF_TOKEN_INVALID = "CSRF_TOKEN_INVALID"

    # Content errors
    CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"
    THEME_NOT_AVAILABLE = "THEME_NOT_AVAILABLE"
    LEVEL_NOT_AVAILABLE = "LEVEL_NOT_AVAILABLE"

    # Rendering errors
    IMAGE_RENDER_FAILED = "IMAGE_RENDER_FAILED"
    LOGO_GENERATION_FAILED = "LOGO_GENERATION_FAILED"

    # Localization errors
    TRANSLATION_NOT_FOUND = "TRANSLATION_NOT_FOUND"
    LANGUAGE_NOT_SUPPORTED = "LANGUAGE_NOT_SUPPORTED"

    # Network errors
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"

    # File operation errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_FAILED = "FILE_READ_FAILED"
    FILE_WRITE_FAILED = "FILE_WRITE_FAILED"


# User-friendly error messages
USER_ERROR_MESSAGES = {
    ErrorCodes.INVALID_THEME: "❌ Неверная тема",
    ErrorCodes.INVALID_LEVEL: "❌ Неверный уровень",
    ErrorCodes.INVALID_LANGUAGE: "❌ Неверный язык",
    ErrorCodes.INVALID_CALLBACK_DATA: "❌ Неизвестная команда",
    ErrorCodes.MISSING_REQUIRED_FIELD: "❌ Отсутствует обязательное поле",
    ErrorCodes.STORAGE_CONNECTION_FAILED: "❌ Ошибка подключения к хранилищу",
    ErrorCodes.SESSION_NOT_FOUND: "❌ Сессия не найдена",
    ErrorCodes.SESSION_SAVE_FAILED: "❌ Ошибка сохранения сессии",
    ErrorCodes.REDIS_CONNECTION_FAILED: "❌ Ошибка подключения к Redis",
    ErrorCodes.TELEGRAM_API_ERROR: "❌ Ошибка Telegram API",
    ErrorCodes.MESSAGE_SEND_FAILED: "❌ Ошибка отправки сообщения",
    ErrorCodes.CALLBACK_ANSWER_FAILED: "❌ Ошибка ответа на callback",
    ErrorCodes.RATE_LIMIT_EXCEEDED: "❌ Превышен лимит запросов",
    ErrorCodes.INVALID_INPUT: "❌ Неверные данные",
    ErrorCodes.CSRF_TOKEN_INVALID: "❌ Неверный токен безопасности",
    ErrorCodes.CONTENT_NOT_FOUND: "❌ Контент не найден",
    ErrorCodes.THEME_NOT_AVAILABLE: "❌ Тема недоступна",
    ErrorCodes.LEVEL_NOT_AVAILABLE: "❌ Уровень недоступен",
    ErrorCodes.IMAGE_RENDER_FAILED: "❌ Ошибка создания изображения",
    ErrorCodes.LOGO_GENERATION_FAILED: "❌ Ошибка создания логотипа",
    ErrorCodes.TRANSLATION_NOT_FOUND: "❌ Перевод не найден",
    ErrorCodes.LANGUAGE_NOT_SUPPORTED: "❌ Язык не поддерживается",
    ErrorCodes.NETWORK_TIMEOUT: "❌ Таймаут сети",
    ErrorCodes.CONNECTION_REFUSED: "❌ Соединение отклонено",
    ErrorCodes.FILE_NOT_FOUND: "❌ Файл не найден",
    ErrorCodes.FILE_READ_FAILED: "❌ Ошибка чтения файла",
    ErrorCodes.FILE_WRITE_FAILED: "❌ Ошибка записи файла",
}


def get_user_error_message(error_code: str, language: str = "ru") -> str:
    """Get user-friendly error message for given error code and language."""
    # For now, return Russian messages. In the future, this can be localized
    return USER_ERROR_MESSAGES.get(error_code, "❌ Неизвестная ошибка")
