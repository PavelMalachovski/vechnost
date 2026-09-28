"""Scheduled jobs that happen once a day, whatever restarts in between.

Three jobs run on a clock: the daily card (a message to every recipient,
minutes of sends), the «69 ступеней» nudge and the retention sweep. They
were `run_daily` jobs on PTB's JobQueue, and three things went wrong:

- a restart in the middle of the daily card lost the rest of the list - the
  job was not resumed and ran again only the next day;
- a restart across the slot lost the day altogether, because APScheduler
  plans the next run from the moment the bot starts and allows a late run
  one second of grace;
- two bots at once - a deploy's overlap - both sent everything.

Now one day's run of a job is a row in `job_runs`, and the row is claimed
before anything is sent or deleted: an INSERT, or a takeover of a row whose
lease has run out, both single statements, so of two processes asking at
once exactly one gets it. The run moves a cursor after every recipient and
renews its lease as it goes. A tick every minute starts whatever is due -
a job whose slot has passed within its window and whose run is not
finished - so a bot that was down at the slot still sends, a bot that died
mid-list is resumed after the last person it reached, and a second bot
finds the row taken. The one person who can hear twice is the one whose
message went out in the instant before a crash, never the whole list.

A bot shutting down hands its run back (the lease is cleared) so the next
process resumes it on its first tick instead of waiting the lease out.

When Sentry is configured each run also checks in with Sentry Crons, under
the job's name, so a push that never started or never finished is an alert
rather than a quiet evening. The check-in id is kept on the row, so a run
resumed by another process closes the check-in its first owner opened.

No python-telegram-bot at import time: the jobs receive whatever bot the
scheduler was given, which is how the tests drive them.
"""

from __future__ import annotations

import logging
import os
import socket
import time as monotonic_clock
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import update

from .payments.database import get_db
from .payments.models import JobRun

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

# How often the scheduler looks for a job that is due. A run starts within
# this of its slot, and a run whose owner died is resumed within this of its
# lease running out.
TICK = timedelta(minutes=1)
# The first look waits for the bot to finish starting.
FIRST_TICK = timedelta(seconds=15)

# How long a claim holds without word from its owner. Every recipient renews
# it, and one recipient can take a couple of minutes when Telegram says to
# wait (`broadcast.deliver` honours `retry_after` up to four times): long
# enough never to be taken from a live owner, short enough that a dead
# owner's list is picked up the same evening.
LEASE = timedelta(minutes=10)

# A run that has been claimed this many times without finishing is left
# alone until its next day: a bug that fails on the same recipient every
# time must not be retried every ten minutes all evening.
MAX_ATTEMPTS = 5

# `job_runs` rows are a few a day and name nobody once a run is over; a
# month of them is enough to see what happened last week.
KEEP = timedelta(days=30)

# Which process holds a claim: host, pid and a random tail, so a restart on
# the same host is a different owner from the one that died.
OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

# What a claim came to (`claim`), and what a run came to (`run_once`).
FRESH = "fresh"  # nobody had started today's run: it is ours
RESUMED = "resumed"  # its owner went quiet: ours, from the cursor on
BUSY = "busy"  # another process holds it and is alive
DONE = "done"  # today's run has finished
GAVE_UP = "gave_up"  # failed MAX_ATTEMPTS times: tomorrow, then
FINISHED = "finished"
STOPPED = "stopped"  # the bot is stopping; the run was handed back
LOST = "lost"  # another process took the run over mid-way
FAILED = "failed"  # raised; resumed once its lease runs out

# The statuses a run counts, the ones `broadcast.deliver` returns.
SENT, BLOCKED = "sent", "blocked"


def utcnow() -> datetime:
    """Naive UTC, like every other timestamp in the schema."""
    return datetime.now(UTC).replace(tzinfo=None)


class LeaseLost(Exception):
    """Another process holds this run now: stop, and touch nothing."""


class Stopping(Exception):
    """The bot is shutting down: hand the run back and stop."""


def _never() -> bool:
    return False


@dataclass
class Run:
    """A claimed run of one job for one day, and how to move it forward.

    A job reads `cursor` to know where to start, calls `check()` before each
    recipient and `advance()` after each one. A run made with
    `Run.detached_for()` has no row behind it - a test, or a job run by hand -
    and moves nothing but itself.
    """

    job: str
    day: date
    owner: str = OWNER
    cursor: int | None = None
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    resumed: bool = False
    check_in_id: str | None = None
    stopping: Callable[[], bool] = field(default=_never, repr=False)
    detached: bool = False

    @classmethod
    def detached_for(cls, job: str, day: date | None = None) -> Run:
        return cls(job=job, day=day or utcnow().date(), detached=True)

    def check(self) -> None:
        """Raise `Stopping` if the bot is on its way down."""
        if self.stopping():
            raise Stopping(self.job)

    async def advance(self, cursor: int, status: str | None = None) -> None:
        """Everything up to `cursor` is done; `status` is how the last one went.

        Renews the lease. Raises `LeaseLost` when the row is no longer this
        run's - its lease ran out and another process took it over - so the
        two never send down the same list.
        """
        if status == SENT:
            self.sent += 1
        elif status == BLOCKED:
            self.blocked += 1
        elif status is not None:
            self.failed += 1
        self.cursor = cursor
        if self.detached:
            return
        async with get_db() as session:
            result = await session.execute(
                update(JobRun)
                .where(*self._mine())
                .values(
                    cursor=cursor,
                    sent=self.sent,
                    blocked=self.blocked,
                    failed=self.failed,
                    lease_until=utcnow() + LEASE,
                )
                .returning(JobRun.job)
            )
            if result.first() is None:
                raise LeaseLost(self.job)

    async def finish(self) -> None:
        """The run is complete. The cursor - a person's id, for the daily
        card - is not kept past the end of the run."""
        if self.detached:
            return
        now = utcnow()
        async with get_db() as session:
            await session.execute(
                update(JobRun)
                .where(*self._mine())
                .values(finished_at=now, cursor=None, lease_until=now)
            )

    async def release(self) -> None:
        """Hand the run back now, rather than when the lease runs out."""
        if self.detached:
            return
        async with get_db() as session:
            await session.execute(update(JobRun).where(*self._mine()).values(lease_until=utcnow()))

    def _mine(self) -> tuple[Any, ...]:
        return (
            JobRun.job == self.job,
            JobRun.day == self.day,
            JobRun.owner == self.owner,
            JobRun.finished_at.is_(None),
        )


def _insert(dialect: str) -> Any:
    """The INSERT that can be told to do nothing on a conflict."""
    if dialect == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.insert
    from sqlalchemy.dialects import sqlite

    return sqlite.insert


async def claim(
    job: str,
    day: date,
    *,
    now: datetime | None = None,
    owner: str = OWNER,
) -> tuple[str, Run | None]:
    """Take `job`'s run for `day`, if it is anybody's to take.

    Returns the outcome and, for FRESH and RESUMED, the run. Each way in is
    one statement - an INSERT that does nothing on a conflict, an UPDATE
    whose WHERE says the lease has run out - so two processes asking at the
    same moment cannot both come away holding the run.
    """
    now = now or utcnow()
    async with get_db() as session:
        bind = session.bind
        assert bind is not None, "get_db() always binds its sessions"
        insert = _insert(bind.dialect.name)
        created = (
            await session.execute(
                insert(JobRun)
                .values(
                    job=job,
                    day=day,
                    owner=owner,
                    lease_until=now + LEASE,
                    attempts=1,
                    sent=0,
                    blocked=0,
                    failed=0,
                    started_at=now,
                )
                .on_conflict_do_nothing(index_elements=["job", "day"])
                .returning(JobRun.job)
            )
        ).first()
        if created is not None:
            return FRESH, Run(job=job, day=day, owner=owner)

        taken = (
            await session.execute(
                update(JobRun)
                .where(
                    JobRun.job == job,
                    JobRun.day == day,
                    JobRun.finished_at.is_(None),
                    JobRun.lease_until < now,
                    JobRun.attempts < MAX_ATTEMPTS,
                )
                .values(owner=owner, lease_until=now + LEASE, attempts=JobRun.attempts + 1)
                .returning(
                    JobRun.cursor,
                    JobRun.sent,
                    JobRun.blocked,
                    JobRun.failed,
                    JobRun.check_in_id,
                )
            )
        ).first()
        if taken is not None:
            return RESUMED, Run(
                job=job,
                day=day,
                owner=owner,
                cursor=taken.cursor,
                sent=taken.sent,
                blocked=taken.blocked,
                failed=taken.failed,
                resumed=True,
                check_in_id=taken.check_in_id,
            )

        row = await session.get(JobRun, (job, day))
        if row is None or row.finished_at is not None:
            return DONE, None
        if row.attempts >= MAX_ATTEMPTS and row.lease_until < now:
            return GAVE_UP, None
        return BUSY, None


@dataclass(frozen=True)
class DailyJob:
    """A job that runs once a day, at `at` (UTC), for up to `window` after.

    The window is how late a run may still start or be resumed: a daily
    card that could not go out by then waits for tomorrow rather than
    arriving in the middle of somebody's night.
    """

    name: str
    at: time
    window: timedelta
    run: Callable[[Any, Run], Awaitable[Any]]

    def due(self, now: datetime) -> date | None:
        """The day whose run should be under way at `now`, if any."""
        for day in (now.date(), now.date() - timedelta(days=1)):
            slot = datetime.combine(day, self.at)
            if slot <= now < slot + self.window:
                return day
        return None

    def monitor_config(self) -> dict[str, Any]:
        """How Sentry Crons should expect this job to check in."""
        return {
            "schedule": {"type": "crontab", "value": f"{self.at.minute} {self.at.hour} * * *"},
            "timezone": "UTC",
            # The tick starts a run within a minute of its slot; a restart
            # across the slot adds a little more.
            "checkin_margin": 15,
            # Nothing resumes a run past its window.
            "max_runtime": int(self.window.total_seconds() // 60),
            "failure_issue_threshold": 1,
            "recovery_threshold": 1,
        }


def _check_in(
    job: DailyJob,
    status: str,
    check_in_id: str | None = None,
    duration: float | None = None,
) -> str | None:
    """Tell Sentry Crons how the run is going; nothing without a DSN."""
    try:
        import sentry_sdk
        from sentry_sdk.crons import capture_checkin

        if not sentry_sdk.get_client().is_active():
            return None
        return capture_checkin(
            monitor_slug=job.name.replace("_", "-"),
            check_in_id=check_in_id,
            status=status,
            duration=duration,
            monitor_config=job.monitor_config(),  # type: ignore[arg-type]
        )
    except Exception as e:
        logger.debug(f"Sentry check-in for {job.name} skipped: {e}")
        return check_in_id


async def _keep_check_in(run: Run, check_in_id: str | None, *, clear: bool = False) -> None:
    """Store the check-in on the row, so a takeover can close it."""
    if (check_in_id is None and not clear) or run.detached:
        return
    async with get_db() as session:
        await session.execute(update(JobRun).where(*run._mine()).values(check_in_id=check_in_id))


async def run_once(
    job: DailyJob,
    day: date,
    *,
    bot: Any,
    stopping: Callable[[], bool] = _never,
    now: datetime | None = None,
) -> str:
    """Claim `job`'s run for `day` and carry it out. Returns what happened:
    one of the claim outcomes when the run was not ours, else FINISHED,
    STOPPED, LOST or FAILED."""
    try:
        outcome, run = await claim(job.name, day, now=now)
    except Exception as e:
        logger.warning(
            f"Job {job.name}: could not claim the run for {day}: {type(e).__name__}: {e}"
        )
        return FAILED
    if run is None:
        if outcome == GAVE_UP:
            logger.error(
                f"Job {job.name}: the run for {day} failed {MAX_ATTEMPTS} times; not retried today"
            )
        return outcome

    run.stopping = stopping
    if run.check_in_id is None:
        run.check_in_id = _check_in(job, "in_progress")
        await _quietly(_keep_check_in(run, run.check_in_id), job, "keep the check-in")
    if run.resumed:
        logger.info(f"Job {job.name}: resuming the run for {day} after {run.cursor}")
    started = monotonic_clock.monotonic()
    try:
        await job.run(bot, run)
        await run.finish()
    except Stopping:
        await _quietly(run.release(), job, "hand the run back")
        logger.info(f"Job {job.name}: stopping; the run for {day} is handed back at {run.cursor}")
        return STOPPED
    except LeaseLost:
        logger.warning(f"Job {job.name}: another process took the run for {day} over")
        return LOST
    except Exception:
        logger.exception(f"Job {job.name} failed for {day}; it is resumed once its lease runs out")
        _check_in(job, "error", run.check_in_id, monotonic_clock.monotonic() - started)
        # That check-in is closed now; whoever resumes the run opens its own.
        await _quietly(_keep_check_in(run, None, clear=True), job, "clear the check-in")
        return FAILED

    _check_in(job, "ok", run.check_in_id, monotonic_clock.monotonic() - started)
    logger.info(
        f"Job {job.name}: the run for {day} is done "
        f"(sent {run.sent}, blocked {run.blocked}, failed {run.failed})"
    )
    return FINISHED


async def _quietly(step: Awaitable[Any], job: DailyJob, what: str) -> None:
    try:
        await step
    except Exception as e:
        logger.warning(f"Job {job.name}: could not {what}: {type(e).__name__}: {e}")


class Scheduler:
    """Starts every daily job that is due, once a minute."""

    def __init__(self, jobs: list[DailyJob]) -> None:
        self.jobs = jobs
        # Runs this process knows are over, so a finished day costs no query
        # a minute for the rest of its window.
        self._settled: set[tuple[str, date]] = set()
        self._running: set[str] = set()

    async def tick(self, application: Application, now: datetime | None = None) -> None:
        now = now or utcnow()
        for job in self.jobs:
            day = job.due(now)
            if day is None or job.name in self._running or (job.name, day) in self._settled:
                continue
            self._running.add(job.name)
            application.create_task(self._run(application, job, day), name=f"job:{job.name}")

    async def _run(self, application: Application, job: DailyJob, day: date) -> None:
        try:
            outcome = await run_once(
                job,
                day,
                bot=application.bot,
                stopping=lambda: not application.running,
            )
            if outcome in (FINISHED, DONE, GAVE_UP):
                self._settled.add((job.name, day))
        finally:
            self._running.discard(job.name)

    async def job_callback(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """The JobQueue entry point: one tick."""
        await self.tick(context.application)


def schedule(application: Application, jobs: list[DailyJob]) -> Scheduler | None:
    """Register the tick that runs `jobs`. Called from `bot.py`."""
    if application.job_queue is None:
        logger.warning(
            "JobQueue is unavailable: the daily card, the 69 steps nudge and "
            "the retention sweep are all disabled; install python-telegram-bot[job-queue]"
        )
        return None
    scheduler = Scheduler(jobs)
    application.job_queue.run_repeating(
        scheduler.job_callback,
        interval=TICK,
        first=FIRST_TICK,
        name="scheduled_jobs",
    )
    for job in jobs:
        logger.info(f"- {job.name} at {job.at:%H:%M} UTC, catching up for {job.window}")
    return scheduler
