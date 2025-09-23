"""Comprehensive test fixtures for Vechnost bot."""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, Optional
import json
import tempfile
import os
from pathlib import Path

from telegram import Update, CallbackQuery, Message, User, Chat
from telegram.ext import ContextTypes

from vechnost_bot.models import SessionState, Language, Theme, ContentType
from vechnost_bot.exceptions import VechnostBotError, ErrorCodes
from vechnost_bot.hybrid_storage import HybridStorage, InMemoryStorage


# ============================================================================
# Session-scoped fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_data_dir():
    """Create temporary directory for test data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


# ============================================================================
# Application fixtures
# ============================================================================

@pytest_asyncio.fixture
async def mock_telegram_bot():
    """Mock Telegram bot instance."""
    bot = MagicMock()
    bot.get_me = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    return bot


@pytest_asyncio.fixture
async def mock_application(mock_telegram_bot):
    """Mock Telegram application."""
    app = MagicMock()
    app.bot = mock_telegram_bot
    app.run_polling = AsyncMock()
    return app


# ============================================================================
# Storage fixtures
# ============================================================================

@pytest_asyncio.fixture
async def in_memory_storage():
    """In-memory storage for testing."""
    return InMemoryStorage()


@pytest_asyncio.fixture
async def hybrid_storage_with_memory():
    """Hybrid storage that uses in-memory storage."""
    storage = HybridStorage()
    # Force use of memory storage
    storage._redis_available = False
    storage._redis_checked = True
    return storage


@pytest_asyncio.fixture
async def mock_redis_storage():
    """Mock Redis storage."""
    storage = AsyncMock()
    storage.connect = AsyncMock()
    storage.disconnect = AsyncMock()
    storage.get_session = AsyncMock()
    storage.save_session = AsyncMock()
    storage.delete_session = AsyncMock()
    storage.cache_image = AsyncMock()
    storage.get_cached_image = AsyncMock()
    storage.increment_counter = AsyncMock()
    storage.get_counter = AsyncMock()
    storage.set_rate_limit = AsyncMock()
    storage.get_rate_limit_info = AsyncMock()
    storage.record_user_activity = AsyncMock()
    storage.get_last_user_activity = AsyncMock()
    storage.health_check = AsyncMock(return_value=True)
    return storage


# ============================================================================
# Telegram API fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_user():
    """Mock Telegram user."""
    user = MagicMock(spec=User)
    user.id = 12345
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.language_code = "en"
    return user


@pytest_asyncio.fixture
def mock_chat():
    """Mock Telegram chat."""
    chat = MagicMock(spec=Chat)
    chat.id = 12345
    chat.type = "private"
    return chat


@pytest_asyncio.fixture
def mock_message(mock_user, mock_chat):
    """Mock Telegram message."""
    message = MagicMock(spec=Message)
    message.message_id = 1
    message.from_user = mock_user
    message.chat = mock_chat
    message.text = "Hello"
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    return message


@pytest_asyncio.fixture
def mock_callback_query(mock_user, mock_chat, mock_message):
    """Mock Telegram callback query."""
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.id = "callback_123"
    callback_query.from_user = mock_user
    callback_query.message = mock_message
    callback_query.data = "theme_Acquaintance"
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    callback_query.edit_message_reply_markup = AsyncMock()
    return callback_query


@pytest_asyncio.fixture
def mock_update(mock_message, mock_callback_query):
    """Mock Telegram update."""
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_message
    update.callback_query = mock_callback_query
    update.effective_user = mock_message.from_user
    update.effective_chat = mock_message.chat
    return update


@pytest_asyncio.fixture
def mock_context():
    """Mock Telegram context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot_data = {}
    context.user_data = {}
    context.chat_data = {}
    return context


# ============================================================================
# Session state fixtures
# ============================================================================

@pytest_asyncio.fixture
def empty_session():
    """Empty session state."""
    return SessionState()


@pytest_asyncio.fixture
def english_session():
    """Session with English language."""
    return SessionState(language=Language.ENGLISH)


@pytest_asyncio.fixture
def russian_session():
    """Session with Russian language."""
    return SessionState(language=Language.RUSSIAN)


@pytest_asyncio.fixture
def czech_session():
    """Session with Czech language."""
    return SessionState(language=Language.CZECH)


@pytest_asyncio.fixture
def acquaintance_session():
    """Session with Acquaintance theme."""
    return SessionState(
        language=Language.ENGLISH,
        theme=Theme.ACQUAINTANCE,
        level=1,
        content_type=ContentType.QUESTIONS
    )


@pytest_asyncio.fixture
def couples_session():
    """Session with For Couples theme."""
    return SessionState(
        language=Language.ENGLISH,
        theme=Theme.FOR_COUPLES,
        level=2,
        content_type=ContentType.QUESTIONS
    )


@pytest_asyncio.fixture
def sex_session():
    """Session with Sex theme."""
    return SessionState(
        language=Language.ENGLISH,
        theme=Theme.SEX,
        level=None,
        content_type=ContentType.QUESTIONS,
        is_nsfw_confirmed=True
    )


@pytest_asyncio.fixture
def provocation_session():
    """Session with Provocation theme."""
    return SessionState(
        language=Language.ENGLISH,
        theme=Theme.PROVOCATION,
        level=None,
        content_type=ContentType.QUESTIONS
    )


# ============================================================================
# Game data fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_game_data():
    """Mock game data."""
    return {
        "themes": {
            "acquaintance": {
                "levels": {
                    "1": ["Question 1", "Question 2", "Question 3"],
                    "2": ["Question 4", "Question 5", "Question 6"],
                    "3": ["Question 7", "Question 8", "Question 9"]
                }
            },
            "for_couples": {
                "levels": {
                    "1": ["Couple Question 1", "Couple Question 2"],
                    "2": ["Couple Question 3", "Couple Question 4"],
                    "3": ["Couple Question 5", "Couple Question 6"]
                }
            },
            "sex": {
                "questions": ["Sex Question 1", "Sex Question 2"],
                "tasks": ["Sex Task 1", "Sex Task 2"]
            },
            "provocation": {
                "questions": ["Provocation Question 1", "Provocation Question 2"]
            }
        }
    }


@pytest_asyncio.fixture
def mock_translations():
    """Mock translations data."""
    return {
        "ru": {
            "themes": {
                "acquaintance": "Знакомства",
                "for_couples": "Для пар",
                "sex": "Секс",
                "provocation": "Провокация"
            },
            "levels": {
                "1": "Уровень 1",
                "2": "Уровень 2",
                "3": "Уровень 3"
            },
            "errors": {
                "unknown_callback": "❌ Неизвестная команда",
                "no_theme": "❌ Тема не выбрана",
                "content_unavailable": "❌ Контент недоступен"
            }
        },
        "en": {
            "themes": {
                "acquaintance": "Acquaintance",
                "for_couples": "For Couples",
                "sex": "Sex",
                "provocation": "Provocation"
            },
            "levels": {
                "1": "Level 1",
                "2": "Level 2",
                "3": "Level 3"
            },
            "errors": {
                "unknown_callback": "❌ Unknown command",
                "no_theme": "❌ Theme not selected",
                "content_unavailable": "❌ Content not available"
            }
        },
        "cs": {
            "themes": {
                "acquaintance": "Seznámení",
                "for_couples": "Pro páry",
                "sex": "Sex",
                "provocation": "Provokace"
            },
            "levels": {
                "1": "Úroveň 1",
                "2": "Úroveň 2",
                "3": "Úroveň 3"
            },
            "errors": {
                "unknown_callback": "❌ Neznámý příkaz",
                "no_theme": "❌ Téma není vybráno",
                "content_unavailable": "❌ Obsah není k dispozici"
            }
        }
    }


# ============================================================================
# File system fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_file_operations():
    """Mock file operations."""
    with patch('vechnost_bot.async_file_ops.aiofiles.open') as mock_open, \
         patch('vechnost_bot.async_file_ops.Path.exists') as mock_exists, \
         patch('vechnost_bot.async_file_ops.Path.mkdir') as mock_mkdir:

        mock_exists.return_value = True
        mock_mkdir.return_value = None

        # Mock file content
        mock_file_content = b"Mock file content"
        mock_open.return_value.__aenter__.return_value.read = AsyncMock(return_value=mock_file_content)
        mock_open.return_value.__aenter__.return_value.write = AsyncMock()

        yield {
            "open": mock_open,
            "exists": mock_exists,
            "mkdir": mock_mkdir
        }


@pytest_asyncio.fixture
def mock_image_operations():
    """Mock image operations."""
    with patch('vechnost_bot.renderer.PIL.Image.open') as mock_pil_open, \
         patch('vechnost_bot.renderer.PIL.Image.new') as mock_pil_new, \
         patch('vechnost_bot.renderer.PIL.ImageDraw.Draw') as mock_draw:

        # Mock PIL Image
        mock_image = MagicMock()
        mock_image.size = (800, 600)
        mock_image.save = MagicMock()
        mock_pil_open.return_value = mock_image
        mock_pil_new.return_value = mock_image

        # Mock ImageDraw
        mock_draw_instance = MagicMock()
        mock_draw_instance.text = MagicMock()
        mock_draw_instance.rectangle = MagicMock()
        mock_draw.return_value = mock_draw_instance

        yield {
            "pil_open": mock_pil_open,
            "pil_new": mock_pil_new,
            "draw": mock_draw,
            "image": mock_image,
            "draw_instance": mock_draw_instance
        }


# ============================================================================
# Environment fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_environment():
    """Mock environment variables."""
    env_vars = {
        "TELEGRAM_BOT_TOKEN": "test_token_12345",
        "LOG_LEVEL": "DEBUG",
        "ENVIRONMENT": "test",
        "REDIS_URL": "redis://localhost:6379",
        "REDIS_DB": "0",
        "REDIS_AUTO_START": "false",
        "SESSION_TTL": "3600",
        "MAX_CONNECTIONS": "10"
    }

    with patch.dict(os.environ, env_vars):
        yield env_vars


# ============================================================================
# Error scenario fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_network_error():
    """Mock network error."""
    return ConnectionError("Connection refused")


@pytest_asyncio.fixture
def mock_redis_error():
    """Mock Redis error."""
    from redis.exceptions import ConnectionError as RedisConnectionError
    return RedisConnectionError("Error 22 connecting to localhost:6379")


@pytest_asyncio.fixture
def mock_telegram_error():
    """Mock Telegram API error."""
    from telegram.error import TelegramError
    return TelegramError("Telegram API error")


@pytest_asyncio.fixture
def mock_validation_error():
    """Mock validation error."""
    from vechnost_bot.exceptions import ValidationError
    return ValidationError(
        "Invalid theme",
        error_code=ErrorCodes.INVALID_THEME,
        field="theme",
        value="invalid_theme"
    )


# ============================================================================
# Performance testing fixtures
# ============================================================================

@pytest_asyncio.fixture
def performance_timer():
    """Timer for performance testing."""
    import time
    start_time = time.time()
    yield lambda: time.time() - start_time


@pytest_asyncio.fixture
def mock_high_load():
    """Mock high load scenario."""
    return {
        "concurrent_users": 100,
        "requests_per_second": 50,
        "session_duration": 300  # 5 minutes
    }


# ============================================================================
# Utility fixtures
# ============================================================================

@pytest_asyncio.fixture
def mock_logger():
    """Mock logger."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    return logger


@pytest_asyncio.fixture
def mock_metrics():
    """Mock metrics collector."""
    metrics = MagicMock()
    metrics.increment_counter = MagicMock()
    metrics.record_timer = MagicMock()
    metrics.record_gauge = MagicMock()
    return metrics


@pytest_asyncio.fixture
def mock_sentry():
    """Mock Sentry client."""
    sentry = MagicMock()
    sentry.capture_exception = MagicMock()
    sentry.set_tag = MagicMock()
    sentry.set_context = MagicMock()
    return sentry


# ============================================================================
# Test data fixtures
# ============================================================================

@pytest_asyncio.fixture
def sample_questions():
    """Sample questions for testing."""
    return [
        "What is your favorite color?",
        "What is your biggest fear?",
        "What is your dream job?",
        "What is your favorite memory?",
        "What is your biggest regret?"
    ]


@pytest_asyncio.fixture
def sample_tasks():
    """Sample tasks for testing."""
    return [
        "Give each other a 5-minute massage",
        "Share your most embarrassing moment",
        "Plan a surprise date for next week",
        "Write each other a love letter",
        "Try a new activity together"
    ]


@pytest_asyncio.fixture
def sample_callback_data():
    """Sample callback data for testing."""
    return {
        "theme_Acquaintance": "theme_Acquaintance",
        "level_1": "level_1",
        "level_2": "level_2",
        "level_3": "level_3",
        "lang_en": "lang_en",
        "lang_ru": "lang_ru",
        "lang_cs": "lang_cs",
        "q:acq:1:0": "q:acq:1:0",
        "q:couples:2:1": "q:couples:2:1",
        "t:sex:0:0": "t:sex:0:0",
        "back:themes": "back:themes",
        "back:levels": "back:levels",
        "back:calendar": "back:calendar"
    }


# ============================================================================
# Integration test fixtures
# ============================================================================

@pytest_asyncio.fixture
async def complete_test_session():
    """Complete test session with all components."""
    session = {
        "storage": await hybrid_storage_with_memory(),
        "bot": await mock_telegram_bot(),
        "app": await mock_application(await mock_telegram_bot()),
        "user": mock_user(),
        "chat": mock_chat(),
        "message": mock_message(mock_user(), mock_chat()),
        "callback_query": mock_callback_query(mock_user(), mock_chat(), mock_message(mock_user(), mock_chat())),
        "update": mock_update(mock_message(mock_user(), mock_chat()), mock_callback_query(mock_user(), mock_chat(), mock_message(mock_user(), mock_chat()))),
        "context": mock_context(),
        "session_state": empty_session(),
        "game_data": mock_game_data(),
        "translations": mock_translations()
    }
    return session


# ============================================================================
# Test configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection."""
    for item in items:
        # Add integration marker to tests in integration_flows.py
        if "integration_flows" in item.nodeid:
            item.add_marker(pytest.mark.integration)

        # Add unit marker to other tests
        else:
            item.add_marker(pytest.mark.unit)

        # Add slow marker to tests that take longer
        if "performance" in item.nodeid or "load" in item.nodeid:
            item.add_marker(pytest.mark.slow)
