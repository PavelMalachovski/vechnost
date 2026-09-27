"""events: what people do, counted, never what they said

One row per event: a name, one allow-listed token (`detail`), the
first-touch `source` an arrival carries, the person and the time - no
answers, texts, names or codes. `/stats` in the bot reads it;
`/delete_me` erases a person's rows and the retention sweep drops them
after `analytics.KEEP`. A new table, so a deploy's `create_all` makes it
with no startup step; this revision is for a database built by
`alembic upgrade head`.

Revision ID: 0da8d9c3add1
Revises: c3d5e7f9a1b2
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0da8d9c3add1"
down_revision: str | None = "c3d5e7f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_events_name_created", "events", ["name", "created_at"])
    op.create_index("idx_events_user_created", "events", ["telegram_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_events_user_created", table_name="events")
    op.drop_index("idx_events_name_created", table_name="events")
    op.drop_table("events")
