"""Database connection and session management."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import event
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from ..config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Built by init_db() on first use (see _engine()).
engine = None
async_session_maker = None


def get_database_url() -> str:
    """Get the async database URL."""
    db_url = settings.database_url
    # Convert sqlite:/// to sqlite+aiosqlite:///
    if db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return db_url


def masked_url(url: str) -> str:
    """The URL with its password replaced, for a log line.

    The full production URL used to be written at INFO on every start,
    which put the database password in the platform's log stream and, via
    Sentry breadcrumbs, in a third party's.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.password:
        return url
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
    return urlunsplit(parts._replace(netloc=netloc))


def _sqlite_in_memory(db_url: str) -> bool:
    """Whether a SQLite URL names a database that lives in its connection."""
    url = make_url(db_url)
    return url.database in (None, "", ":memory:") or url.query.get("mode") == "memory"


def _sqlite_file_engine(db_url: str) -> AsyncEngine:
    """A SQLite file with a connection per session and writers in turn.

    One connection per checkout (`NullPool`), so two requests are two
    transactions rather than one: the `StaticPool` this replaced shared a
    single connection between every request, which interleaved their
    statements in one transaction - under concurrent taps a crowd opening one
    invite seated nobody and six taps turned six cards. NullPool also closes
    each connection in the event loop that opened it, so none outlives its
    loop (a test's, or TestClient's per request).

    Separate connections are not enough on their own. SQLite ignores `FOR
    UPDATE`, and the driver begins a transaction only at the first write, so
    a read-modify-write would read outside any transaction and two of them
    would both write. Every transaction therefore begins IMMEDIATE, taking
    the write lock up front: the next one waits for it (the driver's busy
    timeout), then reads what the first committed. That is the whole file
    rather than one row, which a development database can afford.
    """
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _driver_does_not_begin(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _begin_immediate(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def init_db() -> None:
    """Initialize database engine and session maker."""
    global engine, async_session_maker

    db_url = get_database_url()
    logger.info(f"Initializing database with URL: {masked_url(db_url)}")

    if db_url.startswith("sqlite") and _sqlite_in_memory(db_url):
        # An in-memory database exists only inside its connection, so every
        # session has to share that one: the tests that use one never run
        # two requests at once.
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    elif db_url.startswith("sqlite"):
        engine = _sqlite_file_engine(db_url)
    else:
        engine = create_async_engine(db_url, echo=False)

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    logger.info("Database initialized successfully")


def _engine() -> AsyncEngine:
    """The engine, initialised on first use.

    `init_db()` assigns a module global, which is two statements away from
    every use of it - so each caller opened with `if engine is None:
    init_db()` and then reached for `engine` on trust. This makes it one
    call and one type.
    """
    if engine is None:
        init_db()
    if engine is None:
        raise RuntimeError("Database engine could not be initialised")
    return engine


async def create_tables() -> None:
    """Create all tables, then bring an older database up to the model.

    One transaction per step, and a failing step does not stop the ones
    after it. Postgres aborts a whole transaction on its first failing
    statement, so sharing one would let a single bad DDL discard the work
    that already succeeded. And the steps used to run in one straight line:
    when the access backfill failed on PostgreSQL - on every start, for a
    typing reason SQLite never showed - the webhook release after it never
    ran either, and both failures were logged as "may already exist".
    """
    async with _engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    failed = []
    for step in _STARTUP_STEPS:
        try:
            async with _engine().begin() as conn:
                await conn.run_sync(step)
        except Exception:
            failed.append(step.__name__)
            logger.exception(f"Startup step {step.__name__} failed; continuing with the rest")
    if failed:
        logger.error(f"Database ready, but these startup steps failed: {', '.join(failed)}")
    else:
        logger.info("Database tables created successfully")


# Payments written before this instant come from the code that counted any
# undated payment as lifetime access (64f379a, merged 2026-09-03 15:54 UTC).
# Those are the rows the backfill exists for. Anything newer is a journal
# entry of the current code - a gift bought for someone else, a refund, a
# chargeback - and grants nothing by itself; reading those as access too
# handed a gift's buyer, or a user who charged back, lifetime access on the
# next restart.
ACCESS_FROM_PAYMENTS_CUTOVER = "2026-09-03 16:00:00"


def _backfill_access_from_payments(sync_conn) -> None:
    """Keep the access anyone held when `payments` stopped counting.

    `user_has_access` used to treat any `payments` row without an expiry
    as lifetime access. It no longer does - access is a `subscriptions`
    row - so every user who had access only through such a payment gets
    the equivalent lifetime row here. Only payments from before the
    cutover count, which is what makes this a one-off in effect even
    though it runs on every start: a user it has served now has a
    subscription row, and nothing written later qualifies. A user with any
    subscription row at all is left alone, whatever its status, because
    that row is a decision this backfill must not overturn.

    The NULL is typed on purpose. PostgreSQL types a bare NULL in a
    `SELECT DISTINCT` as text and then refuses to put it in a timestamp
    column, so the untyped version of this statement failed on every
    start of every production process and never backfilled anyone.
    """
    from sqlalchemy import inspect, text

    tables = set(inspect(sync_conn).get_table_names())
    if not {"payments", "subscriptions"} <= tables:
        return
    result = sync_conn.execute(text(
        "INSERT INTO subscriptions "
        "(user_id, subscription_id, period, status, expires_at, last_event_at) "
        "SELECT DISTINCT p.user_id, 0, 'lifetime', 'active', "
        "CAST(NULL AS TIMESTAMP), CURRENT_TIMESTAMP "
        "FROM payments p "
        "WHERE p.expires_at IS NULL "
        f"AND p.created_at < '{ACCESS_FROM_PAYMENTS_CUTOVER}' "
        "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = p.user_id)"
    ))
    if result.rowcount:
        logger.warning(
            f"Backfilled {result.rowcount} lifetime subscription row(s) from "
            "payments that used to count as access on their own"
        )


# A rejected delivery keeps its row with the hash renamed, so the next
# delivery of the same body is not taken for a duplicate.
RELEASED_PREFIX = "released:"


def _release_stuck_webhooks(sync_conn) -> None:
    """Free the hashes of deliveries that were recorded as rejected.

    A webhook refused for its signature used to be written down under the
    body's hash, and Tribute's retry of that body - the same bytes, now
    with a key we accept - was then answered "already processed". Those
    rows are exactly the payments this deployment lost. Renaming their hash
    lets a retry, or a manual redelivery from the Tribute dashboard, land,
    and keeps the row: it is the list of payments to redeliver. This step
    used to delete them, which left that list only in a copy someone had to
    remember to take before the first deploy. The handler no longer writes
    a row for anything it did not process, so after the first run this
    changes nothing.
    """
    from sqlalchemy import inspect, text

    if "webhook_events" not in inspect(sync_conn).get_table_names():
        return
    result = sync_conn.execute(text(
        f"UPDATE webhook_events SET body_sha256 = '{RELEASED_PREFIX}' || body_sha256 "
        f"WHERE status_code >= 400 AND body_sha256 NOT LIKE '{RELEASED_PREFIX}%'"
    ))
    if result.rowcount:
        logger.warning(
            f"Released {result.rowcount} rejected webhook delivery record(s) so "
            "Tribute's retries can be processed. They stay in webhook_events "
            f"with body_sha256 starting '{RELEASED_PREFIX}': redeliver those "
            "payments from the Tribute dashboard"
        )


def _ensure_user_columns(sync_conn) -> None:
    """
    Add columns introduced after the initial schema to pre-existing tables.

    Deploys run create_all (no alembic), which never alters existing tables,
    so new columns are added here idempotently.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    additions = {
        "language": "ALTER TABLE users ADD COLUMN language VARCHAR",
        "daily_card_opt_out": (
            "ALTER TABLE users ADD COLUMN daily_card_opt_out BOOLEAN "
            "NOT NULL DEFAULT '0'"
        ),
        "can_message": (
            "ALTER TABLE users ADD COLUMN can_message BOOLEAN "
            "NOT NULL DEFAULT '1'"
        ),
        # No UNIQUE here: SQLite cannot add a unique column to a populated
        # table, and the code is minted from a uniqueness check in the
        # repository anyway. The model and the migration both declare it, so
        # a database built from either gets the constraint, and
        # `_ensure_indexes` gives a table that got the column here a unique
        # index instead.
        "referral_code": "ALTER TABLE users ADD COLUMN referral_code VARCHAR",
        "referred_by": "ALTER TABLE users ADD COLUMN referred_by BIGINT",
        "referred_at": "ALTER TABLE users ADD COLUMN referred_at TIMESTAMP",
        "partner_telegram_user_id": (
            "ALTER TABLE users ADD COLUMN partner_telegram_user_id BIGINT"
        ),
        "partner_since": "ALTER TABLE users ADD COLUMN partner_since TIMESTAMP",
    }
    for column, ddl in additions.items():
        if column not in existing:
            sync_conn.execute(text(ddl))
            logger.info(f"Added users.{column} column")

    if "referred_at" not in existing:
        # The marker arrives after the invitations it marks: everyone
        # already invited gets it now, in the same transaction as the
        # column, so there is no start on which the column exists and an
        # invited user reads as uninvited. Their join date stands in for
        # the moment of the invitation, which was never recorded.
        result = sync_conn.execute(text(
            "UPDATE users SET referred_at = created_at "
            "WHERE referred_by IS NOT NULL AND referred_at IS NULL"
        ))
        if result.rowcount:
            logger.info(f"Marked {result.rowcount} invited user(s) as referred")


def _ensure_steps69_columns(sync_conn) -> None:
    """Add the per-player columns to a board table created before them.

    «69 ступеней» shipped with one piece for the couple and now has one each,
    so every position, roll count and Joker became two. Deploys run
    create_all, which never alters an existing table, hence this.

    Games already in flight are not migrated: a single shared position cannot
    be split into two without inventing where the second partner was standing.
    Both new positions default to 1, so an unfinished game restarts rather
    than resuming somewhere neither player agreed to.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "steps69_games" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("steps69_games")}
    additions = {
        "creator_position": "ALTER TABLE steps69_games ADD COLUMN creator_position INTEGER NOT NULL DEFAULT 1",
        "guest_position": "ALTER TABLE steps69_games ADD COLUMN guest_position INTEGER NOT NULL DEFAULT 1",
        "creator_piece": "ALTER TABLE steps69_games ADD COLUMN creator_piece VARCHAR",
        "guest_piece": "ALTER TABLE steps69_games ADD COLUMN guest_piece VARCHAR",
        "creator_turns": "ALTER TABLE steps69_games ADD COLUMN creator_turns INTEGER NOT NULL DEFAULT 0",
        "guest_turns": "ALTER TABLE steps69_games ADD COLUMN guest_turns INTEGER NOT NULL DEFAULT 0",
        "creator_joker_task_id": "ALTER TABLE steps69_games ADD COLUMN creator_joker_task_id VARCHAR",
        "guest_joker_task_id": "ALTER TABLE steps69_games ADD COLUMN guest_joker_task_id VARCHAR",
        "last_seat": "ALTER TABLE steps69_games ADD COLUMN last_seat INTEGER",
    }
    for column, ddl in additions.items():
        if column not in existing:
            sync_conn.execute(text(ddl))
            logger.info(f"Added steps69_games.{column} column")


def _ensure_payment_columns(sync_conn: Connection) -> None:
    """Add the columns that keep a Tribute event from applying twice.

    `webhook_events.event_key` identifies an event across redeliveries,
    whose bodies differ in `sent_at`; `certificates.purchase_id` ties a gift
    certificate to the purchase that paid for it, and `revoked_at` records
    that purchase's refund. The first two are unique where set, and an
    index built by create_all on a fresh database is the same one `IF NOT
    EXISTS` finds here, on SQLite and PostgreSQL alike.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    columns = (
        ("webhook_events", "event_key", "VARCHAR"),
        ("certificates", "purchase_id", "VARCHAR"),
        # TIMESTAMP is `timestamp without time zone` on PostgreSQL, the
        # type the model's naive datetimes are stored in.
        ("certificates", "revoked_at", "TIMESTAMP"),
    )
    unique_indexes = (
        ("uq_webhook_events_event_key", "webhook_events", "event_key"),
        ("uq_certificates_purchase_id", "certificates", "purchase_id"),
    )
    for table, column, sql_type in columns:
        if table not in tables:
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
            logger.info(f"Added {table}.{column} column")
    for index, table, column in unique_indexes:
        if table in tables:
            sync_conn.execute(
                text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index} ON {table} ({column})")
            )


def _release_dropped_columns(sync_conn) -> None:
    """Let go of NOT NULL on columns the model no longer has.

    This is the other half of "create_all never alters an existing table",
    and it is the half that bit. When «69 ступеней» went from one piece to
    two, `position`, `turns`, `joker_task_id` and `reactions` left the model.
    create_all does not drop a column, and the step above only adds - so a
    deployment that had already created the table kept three columns that are
    NOT NULL and that nothing fills any more, and **every INSERT failed**:

        null value in column "position" of relation "steps69_games"
        violates not-null constraint

    Reads were fine, which is why the game looked alive right up to the
    moment anyone pressed «Играть»: the board screen drew, and creating a
    board was a 500.

    Note this could not happen with the alembic revision, which writes
    `server_default='1'`. `create_all` reads a model's `default=1` as a
    Python-side default and emits a bare NOT NULL, so the two ways of
    building the same schema disagree exactly here.

    Dropping the constraint rather than the column: the column is dead
    either way, and this is the reversible half. Removing them outright is a
    separate, deliberate migration.
    """
    from sqlalchemy import inspect, text

    if sync_conn.dialect.name == "sqlite":
        # SQLite has no ALTER COLUMN, and a local file is rebuilt rather than
        # migrated. Saying so beats a syntax error inside a transaction that
        # is also creating tables.
        return

    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    for table, model_table in Base.metadata.tables.items():
        if table not in tables:
            continue
        model_columns = {c.name for c in model_table.columns}
        for column in inspector.get_columns(table):
            name = column["name"]
            if name in model_columns or column.get("nullable", True):
                continue
            sync_conn.execute(
                text(f'ALTER TABLE {table} ALTER COLUMN "{name}" DROP NOT NULL')
            )
            logger.warning(
                f"Dropped NOT NULL on {table}.{name}: the column is not in "
                "the model any more, and it was blocking every insert"
            )


def _match_model_nullability(sync_conn: Connection) -> None:
    """Let go of NOT NULL wherever the model says a column may be empty.

    The alembic history and `create_all` disagree about some columns, and
    one disagreement cost money: the first revision made
    `subscriptions.expires_at` NOT NULL, while a lifetime purchase is
    exactly a subscription with no expiry. On a database built by
    `alembic upgrade head` every lifetime grant failed its INSERT, and the
    webhook handler answered Tribute 200. The model is the contract the
    code writes to, so where it allows NULL the database must too.
    PostgreSQL only, like `_release_dropped_columns`.
    """
    from sqlalchemy import inspect, text

    if sync_conn.dialect.name == "sqlite":
        return
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    for table, model_table in Base.metadata.tables.items():
        if table not in tables:
            continue
        nullable_in_model = {c.name for c in model_table.columns if c.nullable}
        for column in inspector.get_columns(table):
            name = column["name"]
            if name in nullable_in_model and not column.get("nullable", True):
                sync_conn.execute(
                    text(f'ALTER TABLE {table} ALTER COLUMN "{name}" DROP NOT NULL')
                )
                logger.warning(f"Dropped NOT NULL on {table}.{name} to match the model")


# Plain indexes the model used to declare on a column that a unique
# constraint already indexes. Each doubled the writes to its column and
# served no read the constraint's own index does not.
REDUNDANT_INDEXES: dict[str, tuple[str, str]] = {
    "idx_telegram_user_id": ("users", "telegram_user_id"),
    "idx_referral_code": ("users", "referral_code"),
    "idx_body_sha256": ("payments", "body_sha256"),
    "idx_body_sha256_webhook": ("webhook_events", "body_sha256"),
    "idx_certificate_code": ("certificates", "code"),
    "idx_room_code": ("rooms", "code"),
    "idx_compat_code": ("compat_tests", "code"),
    "idx_steps69_code": ("steps69_games", "code"),
}


def _unique_on(sync_conn: Connection, table: str, column: str) -> bool:
    """Whether a unique constraint or unique index covers exactly `column`."""
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    if any(uc["column_names"] == [column] for uc in inspector.get_unique_constraints(table)):
        return True
    return any(
        ix.get("unique") and ix["column_names"] == [column]
        for ix in inspector.get_indexes(table)
    )


def _ensure_indexes(sync_conn: Connection) -> None:
    """Give an existing database the model's indexes, and only those.

    `create_all` indexes a table only on the day it creates it, so an index
    added to the model never reached a deployed database - which is how
    `/mine`, `erase` and the retention sweep came to scan whole tables.
    Every index the model declares is created here when missing, and the
    redundant ones are dropped, but only where the unique constraint that
    makes them redundant is actually there to take over.

    `users.referral_code` is the one place it may not be: a table that got
    the column from `_ensure_user_columns` got it without its UNIQUE, and
    with no index at all. It gets a unique index - the model says unique -
    unless the column already holds a duplicate, in which case a plain one
    keeps the lookups off a scan and the log says why.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateIndex

    tables = set(inspect(sync_conn).get_table_names())

    if "users" in tables and not _unique_on(sync_conn, "users", "referral_code"):
        duplicate = sync_conn.execute(text(
            "SELECT referral_code FROM users WHERE referral_code IS NOT NULL "
            "GROUP BY referral_code HAVING COUNT(*) > 1"
        )).first()
        if duplicate is None:
            sync_conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_referral_code "
                "ON users (referral_code)"
            ))
            logger.info("Made users.referral_code unique")
        else:
            sync_conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_referral_code ON users (referral_code)"
            ))
            logger.warning(
                "users.referral_code holds duplicate codes, so it cannot be made "
                "unique; keeping a plain index on it"
            )

    for name, (table, column) in REDUNDANT_INDEXES.items():
        if table in tables and _unique_on(sync_conn, table, column):
            sync_conn.execute(text(f"DROP INDEX IF EXISTS {name}"))

    for model_table in Base.metadata.sorted_tables:
        if model_table.name in tables:
            for index in model_table.indexes:
                sync_conn.execute(CreateIndex(index, if_not_exists=True))


# Run in this order by `create_tables`, each in its own transaction. The
# column steps come first so the index and data steps see the schema they
# expect.
_STARTUP_STEPS = (
    _ensure_user_columns,
    _ensure_steps69_columns,
    _ensure_payment_columns,
    _release_dropped_columns,
    _match_model_nullability,
    _ensure_indexes,
    _backfill_access_from_payments,
    _release_stuck_webhooks,
)


async def drop_tables() -> None:
    """Drop all tables from the database (for testing)."""
    async with _engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped successfully")


_tables_created = False
_tables_lock: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def _creation_lock() -> asyncio.Lock:
    """One lock per event loop: a lock that once waited in a loop is bound to
    it, and the tests run a loop each."""
    global _tables_lock
    loop = asyncio.get_running_loop()
    if _tables_lock is None or _tables_lock[0] is not loop:
        _tables_lock = (loop, asyncio.Lock())
    return _tables_lock[1]


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    global _tables_created

    if async_session_maker is None:
        init_db()

    # Automatically create tables on first access. The steps after
    # create_all report their own failures (see create_tables); what lands
    # here is create_all itself failing, which is never benign.
    # Under a lock: a fresh web process takes several requests at once (the
    # Mini App's boot alone sends three), and each used to run every step
    # beside the others ("table users already exists" on the loser). The
    # others wait for the schema rather than run on half of it.
    if not _tables_created:
        async with _creation_lock():
            if not _tables_created:
                try:
                    await create_tables()
                except Exception as e:
                    logger.error(f"Could not create the database tables: {e}", exc_info=True)
                _tables_created = True  # once per process either way

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Close database connections."""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database connections closed")

