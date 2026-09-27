"""heartbeats: when the bot last proved it was alive

The web process answers `/health/deep` from this table: the bot writes its
row every minute, and a row older than a few minutes means the bot is down
or stuck. A new table, so a deploy's `create_all` makes it with no startup
step; this revision is for a database built by `alembic upgrade head`.

Revision ID: c3d5e7f9a1b2
Revises: b6d0e2f4a8c1
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: str | None = "b6d0e2f4a8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "heartbeats",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("beat_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("heartbeats")
