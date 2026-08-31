"""The half of «create_all never alters a table» that actually bit.

`payments/database.py` adds columns idempotently at startup, because deploys
run `create_all` rather than alembic and `create_all` will not alter a table
that already exists. What it did not do was let go of a column the model had
*stopped* declaring - and «69 ступеней» stopped declaring three of them when
it went from one piece per couple to one per player.

Those three were `nullable=False` with a Python-side `default=`, which
`create_all` writes as a bare NOT NULL with no server default. So a
deployment that had created the table before the change kept three NOT NULL
columns that nothing fills any more, and every INSERT died on

    null value in column "position" of relation "steps69_games"
    violates not-null constraint

Reads were unaffected, so the board screen drew perfectly and pressing
«Играть» was a 500. Note the alembic revision writes `server_default='1'`
and so does not reproduce it: the two ways of building this schema disagree
exactly here, which is why the tests missed it.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from vechnost_bot.payments.database import _release_dropped_columns
from vechnost_bot.payments.models import Steps69Game


def test_create_all_writes_a_python_default_as_a_bare_not_null():
    """The mechanism, in one assertion, without needing a database.

    If SQLAlchemy ever started emitting a server default for `default=`,
    the drift this module guards against would stop existing - and the
    guard could go. Until then it is real.
    """
    metadata = MetaData()
    table = Table(
        "probe", metadata, Column("position", Integer, default=1, nullable=False)
    )
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))

    assert "NOT NULL" in ddl
    assert "DEFAULT" not in ddl, "a server default would have made this harmless"


@pytest.mark.parametrize("column", ["position", "turns", "joker_task_id", "reactions"])
def test_the_one_piece_columns_are_gone_from_the_model(column):
    """They are what the startup step has to release, and only that."""
    assert column not in {c.name for c in Steps69Game.__table__.columns}


def _drift_connection(dialect: str, columns: list[dict]):
    """A connection that reports `columns` for steps69_games and records DDL."""
    conn = MagicMock()
    conn.dialect.name = dialect
    conn.executed = []
    conn.execute.side_effect = lambda stmt: conn.executed.append(str(stmt))

    inspector = MagicMock()
    inspector.get_table_names.return_value = ["steps69_games"]
    inspector.get_columns.return_value = columns
    return conn, inspector


LEGACY_COLUMNS = [
    # What `create_all` left behind on a deployment that predates two pieces.
    {"name": "code", "nullable": False},
    {"name": "position", "nullable": False},
    {"name": "turns", "nullable": False},
    {"name": "reactions", "nullable": False},
    {"name": "joker_task_id", "nullable": True},
    {"name": "creator_position", "nullable": False},
]


def test_the_leftover_not_nulls_are_released():
    """The three that blocked every insert, and nothing else."""
    conn, inspector = _drift_connection("postgresql", LEGACY_COLUMNS)

    with patch("sqlalchemy.inspect", return_value=inspector):
        _release_dropped_columns(conn)

    assert conn.executed == [
        'ALTER TABLE steps69_games ALTER COLUMN "position" DROP NOT NULL',
        'ALTER TABLE steps69_games ALTER COLUMN "turns" DROP NOT NULL',
        'ALTER TABLE steps69_games ALTER COLUMN "reactions" DROP NOT NULL',
    ]


def test_a_column_the_model_still_has_is_left_alone():
    """`code` and `creator_position` are NOT NULL on purpose.

    Releasing those would turn a schema guarantee off, which is the opposite
    of the job: only a column the model has stopped declaring is dead weight.
    """
    conn, inspector = _drift_connection("postgresql", LEGACY_COLUMNS)

    with patch("sqlalchemy.inspect", return_value=inspector):
        _release_dropped_columns(conn)

    assert not any("code" in ddl or "creator_position" in ddl for ddl in conn.executed)


def test_a_nullable_leftover_is_left_alone():
    """`joker_task_id` is dead too, but it is not blocking anything."""
    conn, inspector = _drift_connection("postgresql", LEGACY_COLUMNS)

    with patch("sqlalchemy.inspect", return_value=inspector):
        _release_dropped_columns(conn)

    assert not any("joker_task_id" in ddl for ddl in conn.executed)


def test_sqlite_is_skipped_rather_than_attempted():
    """SQLite has no ALTER COLUMN.

    Attempting it would raise inside the same startup path that creates the
    tables, and `get_db()` swallows that and never retries - so a local
    database would come up quietly half-built.
    """
    conn, inspector = _drift_connection("sqlite", LEGACY_COLUMNS)

    with patch("sqlalchemy.inspect", return_value=inspector):
        _release_dropped_columns(conn)

    assert conn.executed == []


def test_each_startup_step_gets_its_own_transaction():
    """Postgres aborts a whole transaction on the first failing statement.

    Sharing one between create_all and the ensure steps means a single bad
    DDL silently discards the ones that already succeeded - and `get_db()`
    catches the error and sets `_tables_created`, so it never runs again.
    """
    source = Path("vechnost_bot/payments/database.py").read_text()
    body = source.split("async def create_tables()")[1].split("\ndef ")[0]

    assert body.count("_engine().begin()") == 4, (
        "create_all and the three ensure steps each need their own transaction"
    )
