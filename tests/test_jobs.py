"""Scheduled jobs: one run a day, claimed in the database, resumed after a
restart, never repeated by a second bot (`vechnost_bot/jobs.py`).

The three failures these hold: a restart in the middle of the daily card
lost the rest of the list, a restart across the slot lost the day, and two
bots at once (a deploy's overlap) both sent everything.
"""

import asyncio
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest

import vechnost_bot.payments.database as database
from vechnost_bot import jobs
from vechnost_bot.config import settings
from vechnost_bot.jobs import (
    BUSY,
    DONE,
    FAILED,
    FINISHED,
    FRESH,
    GAVE_UP,
    LEASE,
    MAX_ATTEMPTS,
    RESUMED,
    SENT,
    STOPPED,
    DailyJob,
    LeaseLost,
    Run,
    Scheduler,
    claim,
    run_once,
    utcnow,
)
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.models import JobRun

DAY = date(2026, 9, 27)
SLOT = time(17)


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'jobs.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def _row(job: str = "daily_card", day: date = DAY) -> JobRun | None:
    async with get_db() as session:
        return await session.get(JobRun, (job, day))


def later(by: timedelta = LEASE + timedelta(seconds=1)) -> datetime:
    """A moment past a lease taken now."""
    return utcnow() + by


class Audience:
    """A job that sends to a fixed list, after the run's cursor, the way
    the daily card does: `check()` before each person, `advance()` after."""

    def __init__(self, people: list[int], crash_after: int | None = None,
                 crash: BaseException | None = None) -> None:
        self.people = people
        self.crash_after = crash_after
        self.crash = crash or RuntimeError("a bug, on this person")
        self.sent: list[int] = []

    async def __call__(self, bot, run: Run) -> None:
        for person in self.people:
            if run.cursor is not None and person <= run.cursor:
                continue
            run.check()
            self.sent.append(person)
            await run.advance(person, SENT)
            await asyncio.sleep(0)
            if self.crash_after is not None and len(self.sent) == self.crash_after:
                raise self.crash


def daily(run) -> DailyJob:
    return DailyJob("daily_card", SLOT, timedelta(hours=3), run)


# ---------------------------------------------------------------------------
# Claiming a day's run
# ---------------------------------------------------------------------------

async def test_the_first_claim_of_a_day_is_fresh_and_a_second_is_busy(db):
    outcome, run = await claim("daily_card", DAY, owner="a")
    assert outcome == FRESH and run is not None and run.cursor is None

    outcome, run = await claim("daily_card", DAY, owner="b")
    assert (outcome, run) == (BUSY, None)


async def test_a_run_whose_owner_went_quiet_is_taken_over_from_its_cursor(db):
    _, first = await claim("daily_card", DAY, owner="a")
    await first.advance(5, SENT)
    await first.advance(9, "blocked")

    outcome, second = await claim("daily_card", DAY, owner="b", now=later())

    assert outcome == RESUMED
    assert (second.cursor, second.sent, second.blocked, second.resumed) == (9, 1, 1, True)
    row = await _row()
    assert (row.owner, row.attempts) == ("b", 2)


async def test_the_owner_that_lost_its_run_stops_at_the_next_person(db):
    """The one that went quiet was only slow, and comes back: it must not
    send down a list somebody else is now sending down."""
    _, slow = await claim("daily_card", DAY, owner="a")
    await claim("daily_card", DAY, owner="b", now=later())

    with pytest.raises(LeaseLost):
        await slow.advance(1, SENT)


async def test_a_finished_run_is_done_for_the_day_and_tomorrow_is_new(db):
    _, run = await claim("daily_card", DAY, owner="a")
    await run.advance(42, SENT)
    await run.finish()

    assert await claim("daily_card", DAY, owner="b", now=later()) == (DONE, None)
    outcome, _ = await claim("daily_card", DAY + timedelta(days=1), owner="b")
    assert outcome == FRESH
    # The cursor is a person's id: not kept once the run is over.
    assert (await _row()).cursor is None


async def test_a_run_that_keeps_failing_is_left_alone_until_tomorrow(db):
    await claim("daily_card", DAY, owner="a")
    moment = utcnow()
    for attempt in range(2, MAX_ATTEMPTS + 1):
        moment += LEASE + timedelta(seconds=1)
        outcome, _ = await claim("daily_card", DAY, owner=f"o{attempt}", now=moment)
        assert outcome == RESUMED

    moment += LEASE + timedelta(seconds=1)
    assert await claim("daily_card", DAY, owner="last", now=moment) == (GAVE_UP, None)


async def test_a_run_handed_back_is_resumed_without_waiting_out_the_lease(db):
    _, run = await claim("daily_card", DAY, owner="a")
    await run.advance(3, SENT)
    await run.release()

    outcome, resumed = await claim(
        "daily_card", DAY, owner="b", now=utcnow() + timedelta(seconds=1)
    )
    assert outcome == RESUMED and resumed.cursor == 3


async def test_different_jobs_and_days_do_not_share_a_row(db):
    assert (await claim("daily_card", DAY, owner="a"))[0] == FRESH
    assert (await claim("steps69_nudge", DAY, owner="a"))[0] == FRESH
    assert (await claim("daily_card", DAY - timedelta(days=1), owner="a"))[0] == FRESH


# ---------------------------------------------------------------------------
# When a job is due
# ---------------------------------------------------------------------------

def test_a_job_is_due_from_its_slot_to_the_end_of_its_window():
    job = daily(None)
    at = lambda h, m=0: datetime.combine(DAY, time(h, m))  # noqa: E731
    assert job.due(at(16, 59)) is None
    assert job.due(at(17)) == DAY
    assert job.due(at(19, 59)) == DAY
    assert job.due(at(20)) is None, "no daily card in the middle of the night"


def test_a_window_that_crosses_midnight_belongs_to_the_day_it_started():
    job = DailyJob("steps69_nudge", time(23), timedelta(hours=3), None)
    assert job.due(datetime.combine(DAY + timedelta(days=1), time(1))) == DAY
    assert job.due(datetime.combine(DAY + timedelta(days=1), time(2))) is None


# ---------------------------------------------------------------------------
# Running one
# ---------------------------------------------------------------------------

async def test_a_bot_that_was_down_at_the_slot_still_sends_and_only_once(db):
    audience = Audience([1, 2, 3])
    job = daily(audience)

    assert await run_once(job, DAY, bot=None) == FINISHED
    assert await run_once(job, DAY, bot=None) == DONE
    assert audience.sent == [1, 2, 3]


async def test_a_second_bot_finds_the_run_taken_and_sends_nothing(db):
    """A deploy's overlap, one step at a time (the real race, both bots at
    once, runs on PostgreSQL in tests/test_postgres.py: SQLite here shares
    one connection between sessions and cannot hold two at once)."""
    _, first = await claim("daily_card", DAY, owner="old bot")
    await first.advance(1, SENT)

    second = Audience([1, 2, 3])
    assert await run_once(daily(second), DAY, bot=None) == BUSY
    assert second.sent == []


def died() -> BaseException:
    """What a killed process looks like from inside: nothing gets to run
    after it, no `except Exception` and no check-in."""
    return asyncio.CancelledError()


async def test_a_restart_mid_list_resumes_after_the_last_person_reached(db):
    crashed = Audience([1, 2, 3, 4, 5], crash_after=2, crash=died())
    with pytest.raises(asyncio.CancelledError):
        await run_once(daily(crashed), DAY, bot=None)
    assert crashed.sent == [1, 2]

    # A new process, once the dead one's lease has run out.
    restarted = Audience([1, 2, 3, 4, 5])
    assert await run_once(daily(restarted), DAY, bot=None, now=later()) == FINISHED
    assert restarted.sent == [3, 4, 5]
    row = await _row()
    assert (row.sent, row.attempts, row.finished_at is not None) == (5, 2, True)


async def test_a_stopping_bot_hands_its_run_back(db):
    """A redeploy stops the old bot mid-list: it gives the run back, and the
    new one resumes it at its next tick rather than after the lease."""
    audience = Audience([1, 2, 3, 4])
    stopping = iter([False, False, True])
    outcome = await run_once(
        daily(audience), DAY, bot=None, stopping=lambda: next(stopping, True),
    )
    assert outcome == STOPPED and audience.sent == [1, 2]

    rest = Audience([1, 2, 3, 4])
    assert await run_once(
        daily(rest), DAY, bot=None, now=utcnow() + timedelta(seconds=1)
    ) == FINISHED
    assert rest.sent == [3, 4]


# ---------------------------------------------------------------------------
# Sentry Crons
# ---------------------------------------------------------------------------

class Checkins:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, str]] = []

    def __call__(self, monitor_slug=None, check_in_id=None, status=None,
                 duration=None, monitor_config=None):
        assert monitor_config["schedule"] == {"type": "crontab", "value": "0 17 * * *"}
        self.calls.append((monitor_slug, check_in_id, status))
        return check_in_id or f"check-{len(self.calls)}"


@pytest.fixture
def sentry():
    checkins = Checkins()
    client = MagicMock()
    client.is_active.return_value = True
    with (
        patch("sentry_sdk.get_client", return_value=client),
        patch("sentry_sdk.crons.capture_checkin", checkins),
    ):
        yield checkins


async def test_a_run_checks_in_with_sentry_crons(db, sentry):
    await run_once(daily(Audience([1])), DAY, bot=None)
    assert sentry.calls == [
        ("daily-card", None, "in_progress"),
        ("daily-card", "check-1", "ok"),
    ]


async def test_a_failed_run_checks_in_as_an_error(db, sentry):
    await run_once(daily(Audience([1, 2], crash_after=1)), DAY, bot=None)
    assert [status for _, _, status in sentry.calls] == ["in_progress", "error"]


async def test_a_run_resumed_after_a_crash_closes_the_first_check_in(db, sentry):
    """One evening, one check-in, however many processes it took."""
    with pytest.raises(asyncio.CancelledError):
        await run_once(daily(Audience([1, 2], crash_after=1, crash=died())), DAY, bot=None)
    sentry.calls.clear()

    await run_once(daily(Audience([1, 2])), DAY, bot=None, now=later())
    assert sentry.calls == [("daily-card", "check-1", "ok")]


async def test_a_run_resumed_after_an_error_opens_a_check_in_of_its_own(db, sentry):
    """The failure was reported and closed; the retry is a new check-in."""
    assert await run_once(daily(Audience([1, 2], crash_after=1)), DAY, bot=None) == FAILED
    await run_once(daily(Audience([1, 2])), DAY, bot=None, now=later())
    assert [(check, status) for _, check, status in sentry.calls] == [
        (None, "in_progress"), ("check-1", "error"), (None, "in_progress"), ("check-3", "ok"),
    ]


async def test_without_sentry_nothing_checks_in(db):
    with patch("sentry_sdk.crons.capture_checkin") as capture:
        assert await run_once(daily(Audience([1])), DAY, bot=None) == FINISHED
    capture.assert_not_called()
    assert (await _row()).check_in_id is None


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------

class FakeApplication:
    def __init__(self) -> None:
        self.bot = object()
        self.running = True
        self.tasks: list[asyncio.Task] = []

    def create_task(self, coroutine, name=None):
        task = asyncio.ensure_future(coroutine)
        self.tasks.append(task)
        return task


async def test_the_tick_starts_what_is_due_once(db):
    audience = Audience([1, 2])
    scheduler = Scheduler([daily(audience)])
    app = FakeApplication()
    evening = datetime.combine(utcnow().date(), time(17, 30))

    await scheduler.tick(app, now=evening)
    await scheduler.tick(app, now=evening)  # still running: not started twice
    await asyncio.gather(*app.tasks)
    assert len(app.tasks) == 1 and audience.sent == [1, 2]

    await scheduler.tick(app, now=evening + timedelta(minutes=1))
    assert len(app.tasks) == 1, "settled for the day: no query, no task"

    await scheduler.tick(app, now=evening + timedelta(hours=3))
    assert len(app.tasks) == 1, "outside the window"


async def test_the_old_jobs_rows_go_with_the_retention_sweep(db):
    from vechnost_bot.retention import sweep

    _, old = await claim("daily_card", DAY - timedelta(days=40), owner="a",
                         now=utcnow() - timedelta(days=40))
    await old.finish()
    await claim("daily_card", DAY, owner="a")

    assert (await sweep())["job_runs"] == 1
    assert await _row(day=DAY) is not None


def test_the_daily_card_and_the_nudge_run_through_the_scheduler():
    """Both bulk sends take a run, so both are resumable (and the tests of
    each drive them with a detached one)."""
    import inspect

    from vechnost_bot.daily_card import send_daily_cards
    from vechnost_bot.steps69_notify import nudge_stalled_games

    for function in (send_daily_cards, nudge_stalled_games):
        assert "run" in inspect.signature(function).parameters
    assert jobs.OWNER.count(":") == 2
