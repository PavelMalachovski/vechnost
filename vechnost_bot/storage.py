"""Storage abstraction for user sessions with Redis fallback to in-memory."""

import asyncio
from typing import Optional

from .models import SessionState
from .hybrid_storage import get_redis_storage


async def get_session(chat_id: int) -> SessionState:
    """Get or create a session for the given chat ID."""
    storage = await get_redis_storage()
    session = await storage.get_session(chat_id)

    if session is None:
        session = SessionState()
        await storage.save_session(chat_id, session)

    return session


async def reset_session(chat_id: int) -> None:
    """Reset the session for the given chat ID."""
    storage = await get_redis_storage()
    session = await storage.get_session(chat_id)

    if session:
        session.reset()
        await storage.save_session(chat_id, session)
    else:
        # Create new session if none exists
        session = SessionState()
        await storage.save_session(chat_id, session)


async def delete_session(chat_id: int) -> None:
    """Delete a session for the given chat ID."""
    storage = await get_redis_storage()
    await storage.delete_session(chat_id)
