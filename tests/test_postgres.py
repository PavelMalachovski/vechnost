"""What only PostgreSQL shows: the database production runs on.

Every other suite runs on SQLite, which accepted an untyped NULL where
PostgreSQL refuses one, has no ALTER COLUMN, and ignores row locks. So the
startup backfill failed on every production start and no test noticed
(backend audit B-01), and a database built by `alembic upgrade head` could
not take a lifetime purchase (B-05).

These run when POSTGRES_TEST_URL names a server - CI starts one, see
`.github/workflows/e2e.yml` - and are skipped with a reason otherwise. Each
test gets a database of its own, created and dropped around it.
"""

import asyncio
import logging
import os
import secrets
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings

pytestmark = pytest.mark.postgres

ADMIN_URL = os.environ.get("POSTGRES_TEST_URL", "")
REPO = Path(__file__).parent.parent


def _sync(url: str) -> str:
    return url.replace("+asyncpg", "+psycopg2")


@pytest.fixture
def pg_url() -> Iterator[str]:
    """A fresh, empty database on the server POSTGRES_TEST_URL names."""
    if not ADMIN_URL:
        pytest.skip("POSTGRES_TEST_URL is not set (CI sets it; see tests/test_postgres.py)")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    name = f"vechnost_pg_{secrets.token_hex(4)}"
    admin = create_engine(_sync(ADMIN_URL), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _run(url: str, coro_factory):
    """Run app code against `url` with the app's own engine."""
    async def go():
        try:
            return await coro_factory()
        finally:
            await database.close_db()

    with (
        patch.object(settings, "database_url", url),
        patch.object(settings, "enable_payment", True),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        return asyncio.run(go())


def test_every_startup_step_succeeds_on_postgres(pg_url: str, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="vechnost_bot.payments.database")
    _run(pg_url, database.create_tables)
    _run(pg_url, database.create_tables)  # and again, as on the next restart
    assert "failed" not in caplog.text, caplog.text


def test_the_backfill_serves_legacy_customers_on_postgres(pg_url: str) -> None:
    from sqlalchemy import func, select

    from vechnost_bot.payments.models import Subscription, User
    from vechnost_bot.payments.repositories import PaymentRepository, UserRepository
    from vechnost_bot.payments.services import user_has_access

    cutover = datetime.fromisoformat(database.ACCESS_FROM_PAYMENTS_CUTOVER)

    async def seed() -> None:
        await database.create_tables()
        for tg_id, event, when in (
            (920_001, "new_digital_product", cutover - timedelta(days=40)),
            (920_002, "new_digital_product", cutover + timedelta(days=2)),
            (920_003, "chargeback", cutover + timedelta(days=4)),
        ):
            async with database.get_db() as session:
                user = await UserRepository.create_or_update(session, tg_id)
                payment = await PaymentRepository.create(
                    session, provider="tribute", event_name=event, user_id=user.id,
                    telegram_user_id=tg_id, amount=100, currency="rub",
                    raw_body={"name": event}, signature="pg", body_sha256=f"pg-{tg_id}",
                )
                payment.created_at = when

    async def restart_and_read() -> tuple[bool, bool, bool, int]:
        await database.create_tables()
        await database.create_tables()
        async with database.get_db() as session:
            rows = (await session.execute(
                select(func.count()).select_from(Subscription).join(User)
                .where(User.telegram_user_id == 920_001)
            )).scalar_one()
        return (
            await user_has_access(920_001),
            await user_has_access(920_002),
            await user_has_access(920_003),
            int(rows),
        )

    _run(pg_url, seed)
    legacy, gift, chargeback, rows = _run(pg_url, restart_and_read)
    assert legacy is True, "the customer the backfill exists for has access on PostgreSQL"
    assert rows == 1
    assert gift is False and chargeback is False


def test_alembic_builds_a_database_that_takes_a_lifetime_purchase(pg_url: str) -> None:
    """`alembic upgrade head` on PostgreSQL: it used to fail on the async URL
    (MissingGreenlet), then on the untyped NULL, rolling back to no tables;
    and the schema it built refused a subscription without an expiry."""
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    from alembic import command

    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "alembic"))
    with patch.object(settings, "database_url", pg_url):
        command.upgrade(config, "head")

    engine = create_engine(_sync(pg_url))
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("subscriptions")}
        assert columns["expires_at"]["nullable"] is True
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (telegram_user_id, created_at) "
                "VALUES (930001, CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "INSERT INTO subscriptions (user_id, subscription_id, period, status, "
                "expires_at, last_event_at) SELECT id, 0, 'lifetime', 'active', NULL, "
                "CURRENT_TIMESTAMP FROM users WHERE telegram_user_id = 930001"
            ))
    finally:
        engine.dispose()


def test_a_stray_not_null_is_released_at_startup(pg_url: str) -> None:
    """A database that already has the constraint gets it dropped on start."""
    from sqlalchemy import create_engine, inspect, text

    _run(pg_url, database.create_tables)
    engine = create_engine(_sync(pg_url))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subscriptions ALTER COLUMN expires_at SET NOT NULL"))
        _run(pg_url, database.create_tables)
        columns = {c["name"]: c for c in inspect(engine).get_columns("subscriptions")}
        assert columns["expires_at"]["nullable"] is True
    finally:
        engine.dispose()


def test_invitations_before_the_marker_are_kept_on_postgres(pg_url: str) -> None:
    """The deploy that adds `users.referred_at` must mark everyone already
    invited, on the database production runs, or it takes their discount."""
    from sqlalchemy import text

    from vechnost_bot.payments.repositories import UserRepository

    async def seed() -> None:
        await database.create_tables()
        async with database.get_db() as session:
            await UserRepository.create_or_update(session, 940_001)
            await UserRepository.create_or_update(session, 940_002)
            code = await UserRepository.ensure_referral_code(session, 940_001)
            assert code is not None
            assert await UserRepository.record_referral(session, 940_002, code)
        async with database._engine().begin() as conn:
            await conn.execute(text("ALTER TABLE users DROP COLUMN referred_at"))

    async def restart_and_read() -> tuple[bool, bool]:
        await database.create_tables()
        async with database.get_db() as session:
            return (
                await UserRepository.is_referred(session, 940_002),
                await UserRepository.is_referred(session, 940_001),
            )

    _run(pg_url, seed)
    assert _run(pg_url, restart_and_read) == (True, False)


def test_rejected_deliveries_are_kept_and_released_on_postgres(pg_url: str) -> None:
    """The release step renames a hash with `||` and matches with LIKE: both
    have to hold on the database production runs, and twice in a row."""
    from sqlalchemy import select

    from vechnost_bot.payments.models import WebhookEvent
    from vechnost_bot.payments.repositories import WebhookEventRepository

    async def seed() -> None:
        await database.create_tables()
        async with database.get_db() as session:
            for sha, status in (("pg-stuck", 401), ("pg-fine", 200)):
                await WebhookEventRepository.create(
                    session, name="new_digital_product", sent_at=datetime.utcnow(),
                    body_sha256=sha, status_code=status,
                )

    async def restart_twice_and_read() -> list[tuple[str, int]]:
        await database.create_tables()
        await database.create_tables()
        async with database.get_db() as session:
            found = (await session.execute(select(WebhookEvent))).scalars().all()
            return sorted((row.body_sha256, row.status_code) for row in found)

    _run(pg_url, seed)
    assert _run(pg_url, restart_twice_and_read) == [
        ("pg-fine", 200), (database.RELEASED_PREFIX + "pg-stuck", 401),
    ]


def test_the_heartbeat_round_trips_on_postgres(pg_url: str) -> None:
    """The bot writes a naive UTC timestamp and the web process subtracts it
    from its own clock: both halves have to hold on the database production
    runs, and a second beat must update the row rather than collide."""
    from vechnost_bot import heartbeat

    async def beat_twice_and_check() -> tuple[bool, dict]:
        await heartbeat.beat(at=heartbeat.utcnow() - timedelta(minutes=2))
        await heartbeat.beat()
        return await heartbeat.deep_status()

    healthy, checks = _run(pg_url, beat_twice_and_check)
    assert healthy, checks
    assert checks["bot_heartbeat_age_s"] < 60

    async def stale() -> tuple[bool, dict]:
        return await heartbeat.deep_status(now=heartbeat.utcnow() + timedelta(hours=1))

    healthy, checks = _run(pg_url, stale)
    assert not healthy and checks["bot"] == "stale"


def test_the_payment_columns_reach_an_existing_database_on_postgres(pg_url: str) -> None:
    """A database made before the event key, the purchase link and the
    revocation mark got them: the startup step adds the columns and their
    unique indexes, in SQL PostgreSQL accepts, and a second start changes
    nothing."""
    from sqlalchemy import create_engine, inspect, text

    _run(pg_url, database.create_tables)
    engine = create_engine(_sync(pg_url))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE webhook_events DROP COLUMN event_key"))
            conn.execute(text("ALTER TABLE certificates DROP COLUMN purchase_id"))
            conn.execute(text("ALTER TABLE certificates DROP COLUMN revoked_at"))
        _run(pg_url, database.create_tables)
        _run(pg_url, database.create_tables)
        inspector = inspect(engine)
        for table, column, index in (
            ("webhook_events", "event_key", "uq_webhook_events_event_key"),
            ("certificates", "purchase_id", "uq_certificates_purchase_id"),
        ):
            assert column in {c["name"] for c in inspector.get_columns(table)}
            [found] = [i for i in inspector.get_indexes(table) if i["name"] == index]
            assert found["unique"] and found["column_names"] == [column]
        revoked_at = {c["name"]: c for c in inspector.get_columns("certificates")}["revoked_at"]
        assert str(revoked_at["type"]) == "TIMESTAMP" and revoked_at["nullable"] is True
    finally:
        engine.dispose()


def _schema(sync_url: str) -> dict[str, dict[str, tuple[str, bool]]]:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        inspector = inspect(engine)
        return {
            table: {c["name"]: (str(c["type"]), bool(c["nullable"]))
                    for c in inspector.get_columns(table)}
            for table in inspector.get_table_names() if table != "alembic_version"
        }
    finally:
        engine.dispose()


def test_alembic_and_create_all_build_the_same_schema(pg_url: str) -> None:
    """Two ways of building one schema must not disagree.

    Deploys run create_all (plus the startup steps); the docs send a manual
    setup through `alembic upgrade head`. Where the two drifted - a NOT NULL
    here, a server default there - the drift went unnoticed until a payment
    failed, so any column one has and the other lacks, or types or
    nullability that differ, fail here first.
    """
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from alembic import command

    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "alembic"))
    with patch.object(settings, "database_url", pg_url):
        command.upgrade(config, "head")
    by_alembic = _schema(_sync(pg_url))

    indexes_by_alembic = _indexes(_sync(pg_url))

    other = f"vechnost_pg_{secrets.token_hex(4)}"
    admin = create_engine(_sync(ADMIN_URL), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{other}"'))
    try:
        other_url = make_url(pg_url).set(database=other).render_as_string(hide_password=False)
        _run(other_url, database.create_tables)
        by_create_all = _schema(_sync(other_url))
        indexes_by_create_all = _indexes(_sync(other_url))
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{other}" WITH (FORCE)'))
        admin.dispose()

    assert by_alembic == by_create_all
    # And the same indexes, partial predicates included: an index only one
    # build has is a query that scans on the other.
    assert indexes_by_alembic == indexes_by_create_all


def _indexes(sync_url: str) -> dict:
    from sqlalchemy import create_engine

    from tests.test_indexes import index_shape

    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            return index_shape(conn)
    finally:
        engine.dispose()


def test_an_old_database_gets_the_models_indexes_on_postgres(pg_url: str) -> None:
    """The index set before B-23 - eight doubles of unique constraints, none
    of the indexes `/mine`, `erase` and the retention sweep need, and (as on
    a table that got `referral_code` from ALTER TABLE) no unique constraint
    on the code - is brought to exactly what a fresh database has."""
    from sqlalchemy import text

    from tests.test_indexes import ADDED

    async def fresh() -> None:
        await database.create_tables()

    async def make_it_old() -> None:
        async with database._engine().begin() as conn:
            await conn.execute(text(
                "ALTER TABLE users DROP CONSTRAINT users_referral_code_key"
            ))
            for name, (table, column) in database.REDUNDANT_INDEXES.items():
                await conn.execute(text(f"CREATE INDEX {name} ON {table} ({column})"))
            for names in ADDED.values():
                for name in names:
                    await conn.execute(text(f"DROP INDEX {name}"))

    async def restart() -> None:
        await database.create_tables()
        await database.create_tables()

    _run(pg_url, fresh)
    expected = _indexes(_sync(pg_url))
    _run(pg_url, make_it_old)
    old = _indexes(_sync(pg_url))
    assert ("referral_code",) not in old["users"]["unique"]
    assert old != expected
    _run(pg_url, restart)
    assert _indexes(_sync(pg_url)) == expected


def test_the_hot_queries_use_an_index_on_postgres(pg_url: str) -> None:
    """EXPLAIN of the statements the repositories actually send.

    Captured off the engine rather than retyped, so a query rewritten in a
    shape no index serves fails here. Sequential scans are switched off for
    the EXPLAIN: on a near-empty table a scan is the right plan, and the
    question is whether an index *can* serve the query, not whether this
    table is big enough yet to want one.
    """
    from sqlalchemy import event

    from vechnost_bot.payments.repositories import (
        CertificateRepository,
        CompatTestRepository,
        PaymentRepository,
        RetentionRepository,
        RoomRepository,
        Steps69Repository,
        UserRepository,
        WebhookEventRepository,
    )

    now = datetime.utcnow()
    code = "ABCDEFGHJKLMNPQR"
    # (what, the call, the indexes its plan must use)
    queries = [
        ("steps69 /mine", lambda s: Steps69Repository.latest_unfinished_for(s, 1),
         {"idx_steps69_creator", "idx_steps69_guest"}),
        ("compat /mine", lambda s: CompatTestRepository.latest_completed_for(s, 1),
         {"idx_compat_creator", "idx_compat_guest"}),
        ("/invite count", lambda s: UserRepository.count_referrals(s, 1),
         {"idx_users_referred_by"}),
        ("resume nudge", lambda s: Steps69Repository.stalled(s, now, now),
         {"idx_steps69_unfinished_updated"}),
        ("sweep: games", lambda s: RetentionRepository.delete_abandoned_games(s, now),
         {"idx_steps69_unfinished_updated"}),
        ("sweep: tests", lambda s: RetentionRepository.delete_abandoned_compat_tests(s, now),
         {"idx_compat_unfinished_updated"}),
        # What the dropped doubles used to serve, served by the constraints.
        ("user by id", lambda s: UserRepository.get_by_telegram_id(s, 1),
         {"users_telegram_user_id_key"}),
        ("referral code", lambda s: UserRepository.get_by_referral_code(s, "ABC234"),
         {"users_referral_code_key"}),
        ("room code", lambda s: RoomRepository.get_by_code(s, code),
         {"rooms_code_key"}),
        ("test code", lambda s: CompatTestRepository.get_by_code(s, code),
         {"compat_tests_code_key"}),
        ("game code", lambda s: Steps69Repository.get_by_code(s, code),
         {"steps69_games_code_key"}),
        ("certificate", lambda s: CertificateRepository.get_by_code(s, "VECH-XXXX-XXXX"),
         {"certificates_code_key"}),
        ("payment", lambda s: PaymentRepository.get_by_body_sha256(s, "x"),
         {"payments_body_sha256_key"}),
        ("webhook", lambda s: WebhookEventRepository.get_by_body_sha256(s, "x"),
         {"webhook_events_body_sha256_key"}),
    ]
    # erase: every statement that finds a person's rows by participant.
    erase_expects = {
        "DELETE FROM compat_tests": {"idx_compat_creator", "idx_compat_guest"},
        "DELETE FROM steps69_games": {"idx_steps69_creator", "idx_steps69_guest"},
        "UPDATE users SET referred_by": {"idx_users_referred_by"},
        "UPDATE certificates": {"idx_certificate_used_by"},
    }

    async def explain_all() -> dict[str, str]:
        await database.create_tables()
        database._tables_created = True  # or get_db runs them again, captured
        engine = database._engine()
        captured: list[tuple[str, object]] = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            captured.append((statement, parameters))

        plans: dict[str, str] = {}

        async def plan_of(statement: str, parameters: object) -> str:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SET enable_seqscan = off")
                rows = await conn.exec_driver_sql("EXPLAIN " + statement, parameters)
                return "\n".join(row[0] for row in rows)

        event.listen(engine.sync_engine, "before_cursor_execute", capture)
        try:
            for label, call, _ in queries:
                captured.clear()
                async with database.get_db() as session:
                    await call(session)
                [(statement, parameters)] = [
                    c for c in captured if not c[0].lstrip().upper().startswith(
                        ("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")
                    )
                ]
                plans[label] = await plan_of(statement, parameters)
            captured.clear()
            async with database.get_db() as session:
                await UserRepository.erase(session, 1)
            erase_statements = list(captured)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture)
        for prefix in erase_expects:
            [(statement, parameters)] = [
                c for c in erase_statements if c[0].startswith(prefix)
            ]
            plans[prefix] = await plan_of(statement, parameters)
        return plans

    plans = _run(pg_url, explain_all)
    expectations = {label: names for label, _, names in queries} | erase_expects
    for label, names in expectations.items():
        for name in names:
            assert name in plans[label], f"{label} does not use {name}:\n{plans[label]}"
        assert "Seq Scan" not in plans[label], f"{label}:\n{plans[label]}"
