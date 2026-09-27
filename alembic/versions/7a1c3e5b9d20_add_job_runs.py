"""job_runs: one day's run of a scheduled job, claimed and resumable

The daily card, the «69 ступеней» nudge and the retention sweep each claim
their day's row before they touch anything: an INSERT, or a takeover of a
row whose lease has run out. The cursor moves after every recipient, so a
bot that dies mid-list is resumed after the last person it reached, and a
second bot running at the same moment finds the row taken. A new table, so
a deploy's `create_all` makes it with no startup step; this revision is for
a database built by `alembic upgrade head`.

Revision ID: 7a1c3e5b9d20
Revises: 0da8d9c3add1
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a1c3e5b9d20"
down_revision: str | None = "0da8d9c3add1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("job", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("lease_until", sa.DateTime(), nullable=False),
        sa.Column("cursor", sa.BigInteger(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("check_in_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("job", "day"),
    )


def downgrade() -> None:
    op.drop_table("job_runs")
