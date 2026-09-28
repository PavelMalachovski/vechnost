"""What every test gets, and the Telegram doubles the bot tests share."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Settings are constructed when vechnost_bot.config is imported, and the token
# has no default — so without this the whole suite fails to collect on a
# machine (or a CI runner) that has not exported one. A fake token is right:
# nothing here talks to Telegram.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

# And no test may reach a real database. Suites that need one patch
# `settings.database_url` themselves, but a test that simply calls code which
# calls `get_db()` - /start registering the user, for one - used whatever
# DATABASE_URL said: a stray ./vechnost.db in the checkout, or production's
# database for anyone running the suite under `railway run`. Overridden, not
# defaulted, for exactly that reason; one throwaway file per test process.
# (E2E_DATABASE_URL and POSTGRES_TEST_URL are separate, deliberate opt-ins.)
_TEST_DB_DIR = tempfile.mkdtemp(prefix="vechnost-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR}/tests.db"

from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ContextTypes

from vechnost_bot.payments import database as _database
from vechnost_bot.payments import throttle as _throttle

# ============================================================================
# Autouse fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_request_throttle():
    """Give every test a fresh rate-limit budget.

    The throttle's windows are process-global by design, so without this a
    suite that creates more rooms than the hourly budget starts 429ing
    somewhere in the middle and the failure lands on whichever test happened
    to be running. Tests must not inherit each other's counters.
    """
    _throttle.reset()
    yield
    _throttle.reset()


@pytest.fixture(autouse=True)
def _purchases_message_nobody():
    """No test tells a real Telegram that a purchase went through.

    Every signed grant a test delivers to /webhooks/tribute schedules the
    buyer's «всё открыто» message (`payments/grant_notify.py`). With the
    fake token that was a real Bot dialling api.telegram.org after every
    purchase: offline it is a connect timeout per grant, and the two-user
    suite, which buys access for most of its players, took minutes instead
    of seconds. The tests that are about the message patch `_bot` again,
    inside this, and the two-user suite points it at its fake Telegram.
    """
    from vechnost_bot.payments import grant_notify

    with patch.object(grant_notify, "_bot", lambda: None):
        yield


@pytest.fixture(autouse=True)
def _storage_stays_in_memory(request):
    """Every test gets a session store of its own, in memory.

    The store is chosen from REDIS_URL on first use and then kept for the
    life of the process, so without this a machine (or a CI job) that
    exports REDIS_URL would send every test's sessions to that server, and
    whichever test ran first would decide for all the rest in its worker.
    A fresh store per test also means no session leaks from one test into
    the next. Tests that genuinely need a server carry the `redis` marker,
    build their own store, and are left alone here.
    """
    if request.node.get_closest_marker("redis"):
        yield
        return

    from vechnost_bot import storage as _storage

    with patch.object(_storage, "_store", _storage.MemorySessionStore(ttl=3600)):
        yield


@pytest.fixture(autouse=True)
def _database_engines_are_disposed():
    """Every engine the app builds during a test is closed at its end.

    Tests point the app at a database of their own by patching the
    `database.engine` global back to None, so `init_db()` builds a fresh
    engine, and the patch then drops it on the floor. An in-memory SQLite
    engine holds its one aiosqlite connection open, on a worker thread, until
    the garbage collector gets to it - by then the event loop it answered to
    was closed, and the thread died with "Event loop is closed" somewhere
    later in the run. Disposing each engine here closes its connections
    while that can still be done cleanly.
    """
    built = []
    create = _database.create_async_engine

    def recorded(*args, **kwargs):
        engine = create(*args, **kwargs)
        built.append(engine)
        return engine

    with patch.object(_database, "create_async_engine", recorded):
        yield
    for engine in built:
        asyncio.run(engine.dispose())


# ============================================================================
# Sessions
# ============================================================================


@pytest.fixture
def memory_session_store():
    """A session store of the test's own, in memory, as production runs."""
    from vechnost_bot.storage import MemorySessionStore

    return MemorySessionStore(ttl=3600)


# ============================================================================
# Telegram doubles
# ============================================================================


@pytest.fixture
def mock_user():
    """Mock Telegram user."""
    user = MagicMock(spec=User)
    user.id = 12345
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.language_code = "en"
    return user


@pytest.fixture
def mock_chat():
    """Mock Telegram chat."""
    chat = MagicMock(spec=Chat)
    chat.id = 12345
    chat.type = "private"
    return chat


@pytest.fixture
def mock_message(mock_user, mock_chat):
    """Mock Telegram message."""
    message = MagicMock(spec=Message)
    message.message_id = 1
    message.from_user = mock_user
    message.chat = mock_chat
    message.text = "Hello"
    message.photo = ()  # a text message; photo cards set this themselves
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    return message


@pytest.fixture
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


@pytest.fixture
def mock_update(mock_message, mock_callback_query):
    """Mock Telegram update."""
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_message
    update.callback_query = mock_callback_query
    update.effective_user = mock_message.from_user
    update.effective_chat = mock_message.chat
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot_data = {}
    context.user_data = {}
    context.chat_data = {}
    return context


# ============================================================================
# Failures to inject
# ============================================================================


@pytest.fixture
def mock_redis_error():
    """What redis-py raises when the server is not there."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    return RedisConnectionError("Error 22 connecting to localhost:6379")


@pytest.fixture
def mock_telegram_error():
    """What python-telegram-bot raises when the Bot API refuses a call."""
    from telegram.error import TelegramError

    return TelegramError("Telegram API error")


# ============================================================================
# Collection
# ============================================================================


def _redis_is_reachable() -> bool:
    import socket

    try:
        with socket.create_connection(("localhost", 6379), timeout=0.25):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    """Skip the Redis suite, with a reason, when there is no server.

    Those are real integration tests against localhost:6379 — worth keeping
    real, and they do run in CI, where the workflow starts a Redis service.
    On a machine without one they would fail for a reason that has nothing to
    do with the change under test, so the reason is said out loud instead.

    Nothing is marked by name here any more. `slow` used to be added to any
    test whose id contained "load" or "performance", which took nineteen
    ordinary tests (every `*_loads_*`, every `payload`) out of a quick run;
    a slow test now says so itself.
    """
    if not any(item.get_closest_marker("redis") for item in items):
        return
    if _redis_is_reachable():
        return
    skip_redis = pytest.mark.skip(reason="no Redis on localhost:6379 (start one to run these)")
    for item in items:
        if item.get_closest_marker("redis"):
            item.add_marker(skip_redis)
