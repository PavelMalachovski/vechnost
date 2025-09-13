"""In-memory storage for session management."""


from .models import SessionState

# Global session storage - in production, this would be Redis
SESSIONS: dict[int, SessionState] = {}


def get_session(chat_id: int) -> SessionState:
    """Get or create a session for the given chat ID."""
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = SessionState()
    return SESSIONS[chat_id]


def reset_session(chat_id: int) -> None:
    """Reset a session for the given chat ID."""
    if chat_id in SESSIONS:
        SESSIONS[chat_id].reset()
    else:
        SESSIONS[chat_id] = SessionState()


def delete_session(chat_id: int) -> None:
    """Delete a session for the given chat ID."""
    SESSIONS.pop(chat_id, None)
