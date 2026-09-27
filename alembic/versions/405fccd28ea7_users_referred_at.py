"""users.referred_at: an invitation belongs to the invitee

The discounted payment page used to be read from `referred_by`, the link to
the person who sent the invitation. `/delete_me` clears that link when the
inviter asks to be forgotten, so everyone they had invited lost the price
they were promised. `referred_at` is the invitee's own marker; the link can
go without it.

Also applied at startup by `payments/database.py::_ensure_user_columns`,
because deploys run `create_all` rather than alembic.

Revision ID: 405fccd28ea7
Revises: d7f2b4c6e8a0
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "405fccd28ea7"
down_revision: str | None = "d7f2b4c6e8a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("referred_at", sa.DateTime(), nullable=True))
    # Everyone invited before the marker existed. The join date stands in for
    # the moment of the invitation, which was never recorded.
    op.execute(
        "UPDATE users SET referred_at = created_at "
        "WHERE referred_by IS NOT NULL AND referred_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("referred_at")
