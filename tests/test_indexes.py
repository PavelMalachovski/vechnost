"""The indexes the hot queries need, none the unique constraints already give,
and a deployed database brought to both (backend audit B-23).

`/api/steps69/mine`, `/api/compat/mine` and `/delete_me` look a person up as
"creator or guest", and only the creator side of «69 ступеней» was indexed;
`/invite` counted invitations with no index on `referred_by`; the retention
sweep and the resume nudge filtered unfinished rows by `updated_at` with
none. Completed tests and games have no TTL, so each of those was a scan of
every couple who ever played. Meanwhile eight plain indexes sat on columns a
unique constraint already indexes, doubling the writes for nothing.

`create_all` indexes a table only on the day it creates it, so none of this
reaches a deployed database by itself: `database._ensure_indexes` does, and
the tests below hold it to the same result as a database built fresh.
PostgreSQL's side, with the query plans, is in tests/test_postgres.py.
"""

import os
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import UniqueConstraint, inspect, text
from sqlalchemy.exc import IntegrityError

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.models import Base

# The indexes this change adds, by table.
ADDED = {
    "users": {"idx_users_referred_by"},
    "steps69_games": {"idx_steps69_guest", "idx_steps69_unfinished_updated"},
    "compat_tests": {
        "idx_compat_creator", "idx_compat_guest", "idx_compat_unfinished_updated",
    },
}


def index_shape(sync_conn: Any) -> dict[str, Any]:
    """Every table's indexes, comparable across databases and dialects.

    Plain indexes by name, columns and partial predicate. Uniqueness by the
    columns it covers only: a unique constraint is `users_referral_code_key`
    from `create_all`, `uq_users_referral_code` from alembic, and a unique
    index of that name from the startup step - one guarantee, three names.
    """
    inspector = inspect(sync_conn)
    shape: dict[str, Any] = {}
    for table in sorted(inspector.get_table_names()):
        if table == "alembic_version":
            continue
        plain = set()
        unique = {tuple(uc["column_names"]) for uc in inspector.get_unique_constraints(table)}
        for index in inspector.get_indexes(table):
            columns = tuple(index["column_names"])
            if index.get("unique"):
                unique.add(columns)
                continue
            options = index.get("dialect_options", {})
            where = options.get("postgresql_where", options.get("sqlite_where"))
            plain.add((index["name"], columns, None if where is None else str(where)))
        shape[table] = {"plain": plain, "unique": unique}
    return shape


@pytest.fixture
async def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'indexes.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield
        await database.close_db()


async def _shape() -> dict[str, Any]:
    async with database._engine().connect() as conn:
        return await conn.run_sync(index_shape)


async def _execute(*statements: str) -> None:
    async with database._engine().begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_the_model_declares_no_index_a_unique_constraint_already_gives():
    for table in Base.metadata.sorted_tables:
        unique = {
            tuple(c.name for c in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        for index in table.indexes:
            columns = tuple(c.name for c in index.columns)
            assert columns not in unique, f"{index.name} doubles a unique constraint"


def test_the_redundant_list_names_no_index_the_model_still_declares():
    declared = {index.name for table in Base.metadata.sorted_tables for index in table.indexes}
    assert not declared & set(database.REDUNDANT_INDEXES)


@pytest.mark.parametrize("table, column", [
    # "creator or guest": /mine, erase
    ("steps69_games", "creator_telegram_user_id"),
    ("steps69_games", "guest_telegram_user_id"),
    ("compat_tests", "creator_telegram_user_id"),
    ("compat_tests", "guest_telegram_user_id"),
    # /invite's count, erase's unlinking
    ("users", "referred_by"),
    # the retention sweep and the resume nudge, over unfinished rows
    ("steps69_games", "updated_at"),
    ("compat_tests", "updated_at"),
])
def test_what_is_looked_up_by_person_or_by_age_is_indexed(table, column):
    indexed = {
        index.columns[0].name for index in Base.metadata.tables[table].indexes
    }
    assert column in indexed


# --------------------------------------------------------------------------
# A deployed database
# --------------------------------------------------------------------------

async def test_an_old_database_is_brought_to_the_models_indexes(db):
    """The index set of the code before this change - the eight doubles, none
    of the new ones - becomes exactly what a fresh database has, and stays
    so on the next start."""
    await database.create_tables()
    fresh = await _shape()
    for table, names in ADDED.items():
        assert names <= {name for name, _, _ in fresh[table]["plain"]}, table

    await _execute(
        *(
            f"CREATE INDEX {name} ON {table} ({column})"
            for name, (table, column) in database.REDUNDANT_INDEXES.items()
        ),
        *(f"DROP INDEX {name}" for names in ADDED.values() for name in names),
    )
    assert await _shape() != fresh

    await database.create_tables()
    assert await _shape() == fresh
    await database.create_tables()
    assert await _shape() == fresh


# The users table as the first release created it, before any column the
# startup step adds: `referral_code` arrives through ALTER TABLE, which
# cannot carry UNIQUE on SQLite, and so arrived without it in production.
LEGACY_USERS = (
    "CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY, "
    "telegram_user_id BIGINT NOT NULL UNIQUE, username VARCHAR, "
    "first_name VARCHAR, last_name VARCHAR, created_at DATETIME NOT NULL)"
)


async def test_a_referral_code_column_added_at_startup_is_made_unique(db):
    await _execute(
        LEGACY_USERS,
        "INSERT INTO users (telegram_user_id, created_at) VALUES (1, CURRENT_TIMESTAMP)",
        "INSERT INTO users (telegram_user_id, created_at) VALUES (2, CURRENT_TIMESTAMP)",
    )
    await database.create_tables()

    assert ("referral_code",) in (await _shape())["users"]["unique"]
    await _execute("UPDATE users SET referral_code = 'ABC234' WHERE telegram_user_id = 1")
    with pytest.raises(IntegrityError):
        await _execute("UPDATE users SET referral_code = 'ABC234' WHERE telegram_user_id = 2")


async def test_duplicate_codes_keep_a_plain_index_and_the_start_goes_on(db, caplog):
    """Uniqueness cannot be imposed on a column that already breaks it; the
    lookups still get an index, and the step does not fail the start."""
    await _execute(
        LEGACY_USERS,
        "ALTER TABLE users ADD COLUMN referral_code VARCHAR",
        "INSERT INTO users (telegram_user_id, referral_code, created_at) "
        "VALUES (1, 'ABC234', CURRENT_TIMESTAMP)",
        "INSERT INTO users (telegram_user_id, referral_code, created_at) "
        "VALUES (2, 'ABC234', CURRENT_TIMESTAMP)",
    )
    caplog.set_level("WARNING", logger="vechnost_bot.payments.database")
    await database.create_tables()

    users = (await _shape())["users"]
    assert ("referral_code",) not in users["unique"]
    assert ("idx_referral_code", ("referral_code",), None) in users["plain"]
    assert "startup steps failed" not in caplog.text
    assert "duplicate codes" in caplog.text
