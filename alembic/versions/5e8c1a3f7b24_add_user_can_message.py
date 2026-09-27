"""users.can_message: whether the bot can start a conversation with them

False once a send comes back "bot can't initiate conversation" - someone who
never opened a chat with the bot - and true again when they write to it or
allow it to write. The daily card and a broadcast skip the false ones. It
replaces opting such a person out of the daily card, which a later /start
never undid. The startup step adds the column to a deployed table; this
revision is for a database built by `alembic upgrade head`.

Revision ID: 5e8c1a3f7b24
Revises: 7a1c3e5b9d20
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e8c1a3f7b24"
down_revision: str | None = "7a1c3e5b9d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_message", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("users", "can_message")
