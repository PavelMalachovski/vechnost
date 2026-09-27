"""The bot's pulse, written where the web process can read it.

Production runs the web server and the bot as two processes that share
nothing but the database (`run_webhook.py`). So the bot proves it is alive
the only way the other process can see: a row in `heartbeats`, rewritten
every minute by a JobQueue job, and `/health/deep` answers 503 once that row
is older than `STALE_AFTER`.

A job, rather than a line in some handler, because the JobQueue runs on the
bot's own event loop: a bot that has died stops beating, and so does one
that is alive but stuck - a blocking call, a starved connection pool - which
is the failure nothing else would have reported.

`/health` stays light on purpose. It is Railway's healthcheck, and a blip in
the database or a restarting bot must not make Railway refuse a deploy or
recycle a web process that is serving fine; the deep check is for the smoke
test and for whoever is looking.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text

from .payments.database import get_db
from .payments.models import Heartbeat

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

# The row the bot writes. One name per process that beats; there is one.
BOT = "bot"
# How often the bot beats, and how long before the web process gives up on
# it: five missed beats, which no restart or deploy overlap takes.
INTERVAL = timedelta(minutes=1)
STALE_AFTER = timedelta(minutes=5)
# The first beat waits for the bot to finish starting, and keeps the bot's
# first touch of the database clear of the web process's.
FIRST_BEAT = timedelta(seconds=10)
# A database that does not answer SELECT 1 in this long is down, as far as
# a health check is concerned.
DATABASE_TIMEOUT = 5.0


def utcnow() -> datetime:
    """Naive UTC, like every other timestamp in the schema."""
    return datetime.now(UTC).replace(tzinfo=None)


async def beat(name: str = BOT, at: datetime | None = None) -> None:
    """Record that `name` is alive now (or at `at`)."""
    when = at or utcnow()
    async with get_db() as session:
        row = await session.get(Heartbeat, name)
        if row is None:
            session.add(Heartbeat(name=name, beat_at=when))
        else:
            row.beat_at = when


async def heartbeat_job(context: "ContextTypes.DEFAULT_TYPE") -> None:
    """The JobQueue callback. A beat that cannot be written is only logged:
    the database being down is `/health/deep`'s to report, and an error
    here every minute would page nobody and bury everything else."""
    try:
        await beat()
    except Exception as e:
        logger.warning(f"Heartbeat not written: {type(e).__name__}: {e}")


def register_heartbeat(application: "Application") -> None:
    """Make the bot beat. Called from `bot.py` where the jobs are scheduled."""
    if application.job_queue is None:
        logger.warning("JobQueue is unavailable: no heartbeat, /health/deep will report the bot down")
        return
    application.job_queue.run_repeating(
        heartbeat_job, interval=INTERVAL, first=FIRST_BEAT, name="heartbeat"
    )


async def deep_status(now: datetime | None = None) -> tuple[bool, dict[str, Any]]:
    """Whether the database answers and the bot is beating, and the details.

    Only an exception's type is reported, never its text: this answers
    anyone on the internet, and a driver's message can carry a host name or
    a fragment of SQL.
    """
    checks: dict[str, Any] = {}
    try:
        async with asyncio.timeout(DATABASE_TIMEOUT):
            async with get_db() as session:
                await session.execute(text("SELECT 1"))
                last = await session.scalar(
                    select(Heartbeat.beat_at).where(Heartbeat.name == BOT)
                )
    except Exception as e:
        logger.warning(f"Deep health check: the database did not answer: {type(e).__name__}: {e}")
        checks["database"] = f"error: {type(e).__name__}"
        checks["bot"] = "unknown"
        return False, checks
    checks["database"] = "ok"

    if last is None:
        checks["bot"] = "no heartbeat yet"
        return False, checks
    age = ((now or utcnow()) - last).total_seconds()
    checks["bot_heartbeat_age_s"] = round(age)
    if age > STALE_AFTER.total_seconds():
        checks["bot"] = "stale"
        return False, checks
    checks["bot"] = "ok"
    return True, checks
