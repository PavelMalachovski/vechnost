"""Storage abstraction for user sessions."""

import asyncio
from typing import Optional

from .models import SessionState
from .redis_storage import get_redis_storage


async def get_session(chat_id: int) -> SessionState:
    """Get or create a session for the given chat ID."""
    redis_storage = await get_redis_storage()
    session = await redis_storage.get_session(chat_id)

    if session is None:
        session = SessionState()
        await redis_storage.save_session(chat_id, session)

    return session


async def reset_session(chat_id: int) -> None:
    """Reset the session for the given chat ID."""
    redis_storage = await get_redis_storage()
    session = await redis_storage.get_session(chat_id)

    if session:
        session.reset()
        await redis_storage.save_session(chat_id, session)
    else:
        # Create new session if none exists
        session = SessionState()
        await redis_storage.save_session(chat_id, session)


async def delete_session(chat_id: int) -> None:
    """Delete a session for the given chat ID."""
    redis_storage = await get_redis_storage()
    await redis_storage.delete_session(chat_id)
