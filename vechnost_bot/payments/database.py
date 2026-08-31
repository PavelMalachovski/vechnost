"""Database connection and session management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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


def init_db() -> None:
    """Initialize database engine and session maker."""
    global engine, async_session_maker

    db_url = get_database_url()
    logger.info(f"Initializing database with URL: {db_url}")

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


async def create_tables() -> None:
    """Create all tables in the database."""
    if engine is None:
        init_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_user_columns)
        await conn.run_sync(_ensure_steps69_columns)
    logger.info("Database tables created successfully")


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


async def drop_tables() -> None:
    """Drop all tables from the database (for testing)."""
    if engine is None:
        init_db()

    async with engine.begin() as conn:
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

