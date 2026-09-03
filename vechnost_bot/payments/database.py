"""Database connection and session management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from ..config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Create async engine
# For SQLite, we need to use aiosqlite and ensure thread-safe access
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


def init_db() -> None:
    """Initialize database engine and session maker."""
    global engine, async_session_maker

    db_url = get_database_url()
    logger.info(f"Initializing database with URL: {masked_url(db_url)}")

    # For SQLite, use StaticPool to ensure thread-safe access
    if "sqlite" in db_url:
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
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
    """Create all tables in the database."""
    # One transaction each, on purpose. Postgres aborts a whole transaction
    # on the first failing statement, so sharing one means a single bad DDL
    # silently discards the work that already succeeded - and `get_db()`
    # swallows the exception and never retries, which would make that
    # permanent for the life of the process.
    async with _engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _engine().begin() as conn:
        await conn.run_sync(_ensure_user_columns)
    async with _engine().begin() as conn:
        await conn.run_sync(_ensure_steps69_columns)
    async with _engine().begin() as conn:
        await conn.run_sync(_release_dropped_columns)
    async with _engine().begin() as conn:
        await conn.run_sync(_backfill_access_from_payments)
    async with _engine().begin() as conn:
        await conn.run_sync(_release_stuck_webhooks)
    logger.info("Database tables created successfully")


def _backfill_access_from_payments(sync_conn) -> None:
    """Keep the access anyone holds today when `payments` stops counting.

    `user_has_access` used to treat any `payments` row without an expiry
    as lifetime access. It no longer does - access is a `subscriptions`
    row - so every user who had access only through such a payment gets
    the equivalent lifetime row here, once. Idempotent: a user with any
    subscription row at all is left alone, whatever its status, because
    that row is a decision this backfill must not overturn.
    """
    from sqlalchemy import inspect, text

    tables = set(inspect(sync_conn).get_table_names())
    if not {"payments", "subscriptions"} <= tables:
        return
    result = sync_conn.execute(text(
        "INSERT INTO subscriptions "
        "(user_id, subscription_id, period, status, expires_at, last_event_at) "
        "SELECT DISTINCT p.user_id, 0, 'lifetime', 'active', NULL, CURRENT_TIMESTAMP "
        "FROM payments p "
        "WHERE p.expires_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = p.user_id)"
    ))
    if result.rowcount:
        logger.warning(
            f"Backfilled {result.rowcount} lifetime subscription row(s) from "
            "payments that used to count as access on their own"
        )


def _release_stuck_webhooks(sync_conn) -> None:
    """Forget deliveries that were recorded as rejected.

    A webhook refused for its signature used to be written down under the
    body's hash, and Tribute's retry of that body - the same bytes, now
    with a key we accept - was then answered "already processed". Those
    rows are exactly the payments this deployment lost. Deleting them lets
    a retry, or a manual redelivery from the Tribute dashboard, land. The
    handler no longer writes a row for anything it did not process, so
    after the first run this deletes nothing.
    """
    from sqlalchemy import inspect, text

    if "webhook_events" not in inspect(sync_conn).get_table_names():
        return
    result = sync_conn.execute(
        text("DELETE FROM webhook_events WHERE status_code >= 400")
    )
    if result.rowcount:
        logger.warning(
            f"Released {result.rowcount} rejected webhook delivery record(s) so "
            "Tribute's retries can be processed"
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
        # No UNIQUE here: SQLite cannot add a unique column to a populated
        # table, and the code is minted from a uniqueness check in the
        # repository anyway. The model and the migration both declare it, so
        # a database built from either gets the constraint.
        "referral_code": "ALTER TABLE users ADD COLUMN referral_code VARCHAR",
        "referred_by": "ALTER TABLE users ADD COLUMN referred_by BIGINT",
    }
    for column, ddl in additions.items():
        if column not in existing:
            sync_conn.execute(text(ddl))
            logger.info(f"Added users.{column} column")


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


async def drop_tables() -> None:
    """Drop all tables from the database (for testing)."""
    async with _engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped successfully")


_tables_created = False

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    global _tables_created

    if async_session_maker is None:
        init_db()

    # Automatically create tables on first access
    if not _tables_created:
        try:
            await create_tables()
            _tables_created = True
        except Exception as e:
            logger.warning(f"Error creating tables (may already exist): {e}")
            _tables_created = True  # Don't try again

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

