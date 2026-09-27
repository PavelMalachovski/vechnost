"""/stats: the funnel, read off the `events` table.

Every number here is people, not taps, unless it says sessions: a person
who opened the paywall five times is one person who saw it. Two windows,
the last 7 days and the last 30, side by side, and one cohort line for
coming back. Sources are first touch - the channel on a person's first
arrival - so a person who first came by `src_tiktok` and later by a
referral link counts for TikTok.

Reads through `collect()` and writes through `render()`; neither imports
python-telegram-bot, so the report can be tested and printed without a bot.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, select

from .analytics import ACTIVATIONS, ARRIVALS, JOINS

WINDOWS = (7, 30)
# The cohort the return line is measured on: people who first came between
# COHORT_FROM and COHORT_TO days ago, old enough to have had a day 7.
COHORT_FROM, COHORT_TO = 37, 8
TOP_SOURCES = 6
NO_SOURCE = "без метки"


@dataclass
class Window:
    days: int
    new_people: int = 0
    active_people: int = 0
    activated: int = 0
    sources: list[tuple[str, int]] = field(default_factory=list)
    # name -> (events, distinct people)
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    doors: list[tuple[str, int]] = field(default_factory=list)

    def events(self, name: str) -> int:
        return self.counts.get(name, (0, 0))[0]

    def people(self, name: str) -> int:
        return self.counts.get(name, (0, 0))[1]


@dataclass
class Report:
    now: datetime
    windows: list[Window]
    cohort: int = 0
    back_day1: int = 0
    back_day7: int = 0


async def collect(now: datetime | None = None) -> Report:
    """Everything the report prints, in a handful of queries."""
    from .payments.database import get_db
    from .payments.models import AnalyticsEvent as E

    now = now or datetime.utcnow()
    longest = max(WINDOWS)

    async with get_db() as session:
        # When each person was first seen, over everything still kept.
        first_rows = await session.execute(
            select(E.telegram_user_id, func.min(E.created_at))
            .where(E.telegram_user_id.is_not(None))
            .group_by(E.telegram_user_id)
        )
        first_seen: dict[int, datetime] = {
            uid: at for uid, at in first_rows.all() if uid is not None
        }

        # The channel on each person's first arrival in the longest window.
        arrivals = await session.execute(
            select(E.telegram_user_id, E.created_at, E.source)
            .where(E.name.in_(ARRIVALS), E.created_at >= now - timedelta(days=longest + 1))
            .order_by(E.created_at)
        )
        first_source: dict[int, str | None] = {}
        for uid, _at, source in arrivals.all():
            if uid is not None and uid not in first_source:
                first_source[uid] = source

        # The first activation of each person active in the longest window.
        activations = await session.execute(
            select(E.telegram_user_id, func.min(E.created_at))
            .where(
                E.name.in_(ACTIVATIONS),
                E.created_at >= now - timedelta(days=longest + 1),
                E.telegram_user_id.is_not(None),
            )
            .group_by(E.telegram_user_id)
        )
        first_activation: dict[int, datetime] = {
            uid: at for uid, at in activations.all() if uid is not None
        }

        windows = []
        for days in WINDOWS:
            since = now - timedelta(days=days)
            window = Window(days=days)

            new = [uid for uid, at in first_seen.items() if at >= since]
            window.new_people = len(new)
            window.activated = sum(
                1 for uid in new
                if uid in first_activation
                and first_activation[uid] - first_seen[uid] <= timedelta(days=1)
            )
            by_source: dict[str, int] = {}
            for uid in new:
                key = first_source.get(uid) or NO_SOURCE
                by_source[key] = by_source.get(key, 0) + 1
            window.sources = sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0]))

            active = await session.execute(
                select(func.count(distinct(E.telegram_user_id))).where(E.created_at >= since)
            )
            window.active_people = int(active.scalar() or 0)

            counts = await session.execute(
                select(E.name, func.count(), func.count(distinct(E.telegram_user_id)))
                .where(E.created_at >= since)
                .group_by(E.name)
            )
            window.counts = {name: (int(n), int(p)) for name, n, p in counts.all()}

            doors = await session.execute(
                select(E.detail, func.count(distinct(E.telegram_user_id)))
                .where(E.name == "paywall_view", E.created_at >= since)
                .group_by(E.detail)
            )
            window.doors = sorted(
                ((door or "?", int(p)) for door, p in doors.all()),
                key=lambda kv: (-kv[1], kv[0]),
            )
            windows.append(window)

        # Coming back: of the people first seen COHORT_FROM..COHORT_TO days
        # ago, who was here again on their day 1 and on their day 7.
        cohort_from = now - timedelta(days=COHORT_FROM)
        cohort_to = now - timedelta(days=COHORT_TO)
        cohort = {
            uid: at for uid, at in first_seen.items() if cohort_from <= at < cohort_to
        }
        seen_on: set[tuple[int, int]] = set()
        if cohort:
            # Only the cohort, and only as far as its latest member's day 7.
            days_active = await session.execute(
                select(E.telegram_user_id, E.created_at).where(
                    E.telegram_user_id.in_(list(cohort)),
                    E.created_at >= cohort_from,
                    E.created_at < cohort_to + timedelta(days=8),
                )
            )
            for uid, at in days_active.all():
                if uid is None:
                    continue
                start = cohort[uid]
                seen_on.add((uid, (at.date() - start.date()).days))

    report = Report(now=now, windows=windows, cohort=len(cohort))
    report.back_day1 = sum(1 for uid in cohort if (uid, 1) in seen_on)
    report.back_day7 = sum(1 for uid in cohort if (uid, 7) in seen_on)
    return report


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "–"


DOOR_NAMES = {
    "deck": "конец бесплатных карт",
    "room": "комната вдвоём",
    "compat": "тест совместимости",
    "s69": "69 ступеней",
    "library": "практики",
    "guide": "мастер-класс",
}


def render(report: Report) -> str:
    """The report as the bot sends it: plain text, two windows side by side."""
    week, month = report.windows[0], report.windows[1]

    def pair(get: Callable[[Window], Any]) -> str:
        return f"{get(week)} / {get(month)}"

    lines = [
        f"📊 VECHNOST: 7 / 30 дней (на {report.now:%d.%m %H:%M} UTC)",
        "",
        f"Новые люди: {pair(lambda w: w.new_people)}",
        f"Активные: {pair(lambda w: w.active_people)}",
        "Активация в первый день: "
        + pair(lambda w: _pct(w.activated, w.new_people)),
        "",
        "Откуда пришли (30 дней):",
    ]
    sources = month.sources[:TOP_SOURCES]
    if sources:
        lines += [f"  {name}: {count}" for name, count in sources]
        rest = sum(count for _, count in month.sources[TOP_SOURCES:])
        if rest:
            lines.append(f"  остальные: {rest}")
    else:
        lines.append("  пока никого")

    def sessions(w: Window) -> int:
        return w.events("room_create") + w.events("compat_create") + w.events("s69_create")

    def joins(w: Window) -> int:
        return sum(w.events(name) for name in JOINS)

    lines += [
        "",
        "Вдвоём:",
        f"  сессий создано: {pair(sessions)}",
        f"  партнёр зашёл: {pair(joins)} ({pair(lambda w: _pct(joins(w), sessions(w)))})",
        f"  приглашений отправлено: {pair(lambda w: w.events('invite_share'))}",
        f"  тестов совместимости пройдено: {pair(lambda w: w.events('compat_done'))}",
        "",
        "Оплата (люди):",
        f"  увидели пейвол: {pair(lambda w: w.people('paywall_view'))}",
        f"  нажали «Открыть всё»: {pair(lambda w: w.people('buy_click'))}"
        f" ({pair(lambda w: _pct(w.people('buy_click'), w.people('paywall_view')))})",
        f"  оплатили: {pair(lambda w: w.people('purchase'))}"
        f" ({pair(lambda w: _pct(w.people('purchase'), w.people('buy_click')))})",
        f"  подарков: {pair(lambda w: w.events('gift_purchase'))},"
        f" возвратов: {pair(lambda w: w.events('refund'))}",
    ]
    if month.doors:
        lines.append("  где видели пейвол (30 дней): " + ", ".join(
            f"{DOOR_NAMES.get(door, door)} {count}" for door, count in month.doors
        ))
    lines += [
        "",
        f"Вернулись (пришли {COHORT_FROM}–{COHORT_TO} дней назад, {report.cohort} чел.):",
        f"  на 1-й день: {_pct(report.back_day1, report.cohort)},"
        f" на 7-й день: {_pct(report.back_day7, report.cohort)}",
    ]
    return "\n".join(lines)


async def stats_command(update: Any, context: Any) -> None:
    """/stats, for the people ADMIN_IDS names and nobody else.

    Registered only where ADMIN_IDS names somebody (like /broadcast), and
    the id is checked again here rather than trusted to the registration.
    """
    from .config import settings

    user = update.effective_user
    message = update.effective_message
    if user is None or message is None or user.id not in settings.admin_user_ids:
        return
    try:
        text = render(await collect())
    except Exception as e:
        text = f"Статистика сейчас недоступна: {type(e).__name__}"
    await message.reply_text(text)
