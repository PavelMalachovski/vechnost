"""Database connection and session management."""

import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
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
    }
    for column, ddl in additions.items():
        if column not in existing:
            sync_conn.execute(text(ddl))
            logger.info(f"Added users.{column} column")


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

