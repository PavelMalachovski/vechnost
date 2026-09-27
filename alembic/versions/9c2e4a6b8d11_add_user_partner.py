"""users.partner_telegram_user_id: who each person last played with

Set both ways when a guest takes the empty seat in a room, a compatibility
test or a «69 ступеней» board, so each of the two knows the other outside
any one game; cleared on the other side when either asks to be forgotten.
The startup step adds the columns to a deployed table and `_ensure_indexes`
the partial index; this revision is for a database built by `alembic
upgrade head`.

Revision ID: 9c2e4a6b8d11
Revises: 7a1c3e5b9d20
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c2e4a6b8d11"
down_revision: str | None = "7a1c3e5b9d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _partial(where: sa.ColumnElement[bool]) -> dict[str, sa.ColumnElement[bool]]:
    """The same WHERE for both dialects, as the model spells it."""
    return {"postgresql_where": where, "sqlite_where": where}


def upgrade() -> None:
    op.add_column("users", sa.Column("partner_telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("partner_since", sa.DateTime(), nullable=True))
    op.create_index(
        "idx_users_partner", "users", ["partner_telegram_user_id"],
        **_partial(sa.column("partner_telegram_user_id").is_not(None)),
    )


def downgrade() -> None:
    op.drop_index("idx_users_partner", table_name="users")
    op.drop_column("users", "partner_since")
    op.drop_column("users", "partner_telegram_user_id")
