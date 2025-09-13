"""Tests for storage module."""

from vechnost_bot.models import SessionState
from vechnost_bot.storage import SESSIONS, delete_session, get_session, reset_session


class TestStorage:
    """Test storage functionality."""

    def setup_method(self):
        """Clear sessions before each test."""
        SESSIONS.clear()

    def test_get_session_new(self):
        """Test getting a new session."""
        chat_id = 12345
        session = get_session(chat_id)

        assert isinstance(session, SessionState)
        assert chat_id in SESSIONS
        assert SESSIONS[chat_id] is session

    def test_get_session_existing(self):
        """Test getting an existing session."""
        chat_id = 12345
        session1 = get_session(chat_id)
        session2 = get_session(chat_id)

        assert session1 is session2
        assert len(SESSIONS) == 1

    def test_reset_session_existing(self):
        """Test resetting an existing session."""
        chat_id = 12345
        session = get_session(chat_id)
        session.theme = "Acquaintance"
        session.level = 1

        reset_session(chat_id)

        assert session.theme is None
        assert session.level is None
        assert chat_id in SESSIONS

    def test_reset_session_new(self):
        """Test resetting a non-existing session."""
        chat_id = 12345

        reset_session(chat_id)

        assert chat_id in SESSIONS
        assert isinstance(SESSIONS[chat_id], SessionState)

    def test_delete_session_existing(self):
        """Test deleting an existing session."""
        chat_id = 12345
        get_session(chat_id)

        assert chat_id in SESSIONS

        delete_session(chat_id)

        assert chat_id not in SESSIONS

    def test_delete_session_non_existing(self):
        """Test deleting a non-existing session."""
        chat_id = 12345

        # Should not raise an error
        delete_session(chat_id)

        assert chat_id not in SESSIONS
