"""Deleting the rows nobody is coming back for.

Three tables hold what couples said and did, and none of them had anything
that removed a row. A room becomes unreachable the moment its 24-hour TTL
passes, but the row stayed forever; an unfinished compatibility test and an
abandoned board stayed with it. Keeping intimate answers indefinitely because
nobody wrote the delete is not a retention policy, it is an oversight.

What is *not* deleted matters as much: a finished compatibility test and a
finished game are kept, because both are meant to be re-read months later and
that is exactly why neither has a TTL.

Imports neither FastAPI nor python-telegram-bot beyond the job entry point,
so the sweep can be run from a script as easily as from the scheduler.
"""

import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# A room is already unreachable at 24 hours; the extra day is slack for a
# clock skew or a job that did not run, not a second chance at reading it.
ROOM_KEEP = timedelta(hours=48)

# Long enough that "we will finish it next month" is still true, short enough
# that it is not indefinite. The resume nudge gives up after a week.
ABANDONED_KEEP = timedelta(days=90)


async def sweep(now: datetime | None = None) -> dict[str, int]:
    """Delete what is past keeping. Returns what went, by kind."""
    from .payments.database import get_db
    from .payments.repositories import RetentionRepository

    now = now or datetime.utcnow()
    async with get_db() as session:
        removed = {
            "rooms": await RetentionRepository.delete_expired_rooms(
                session, now - ROOM_KEEP
            ),
            "compat_tests": await RetentionRepository.delete_abandoned_compat_tests(
                session, now - ABANDONED_KEEP
            ),
            "games": await RetentionRepository.delete_abandoned_games(
                session, now - ABANDONED_KEEP
            ),
        }

    if any(removed.values()):
        logger.info(f"Retention sweep removed {removed}")
    return removed


async def retention_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB JobQueue entry point."""
    await sweep()
