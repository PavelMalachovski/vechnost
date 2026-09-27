"""Index what `/mine`, `erase` and the retention sweep ask; drop the doubles

`/api/steps69/mine`, `/api/compat/mine` and `/delete_me` look a person up as
"creator or guest", and only the creator side of «69 ступеней» had an index;
counting a user's invitations had none; the retention sweep and the resume
nudge filter unfinished rows by `updated_at` with none. Finished tests and
games have no TTL, so those scans grow with every couple who ever played.

Eight plain indexes sat on columns a unique constraint already indexes and
only doubled the writes; they go.

Also applied at startup by `payments/database.py::_ensure_indexes`, because
deploys run `create_all` rather than alembic.

Revision ID: b307ad68d9dc
Revises: 405fccd28ea7
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "b307ad68d9dc"
down_revision: str | None = "405fccd28ea7"
branch_labels = None
depends_on = None

# (name, table, column): each duplicates the unique constraint on its column.
REDUNDANT = (
    ("idx_telegram_user_id", "users", "telegram_user_id"),
    ("idx_referral_code", "users", "referral_code"),
    ("idx_body_sha256", "payments", "body_sha256"),
    ("idx_body_sha256_webhook", "webhook_events", "body_sha256"),
    ("idx_certificate_code", "certificates", "code"),
    ("idx_room_code", "rooms", "code"),
    ("idx_compat_code", "compat_tests", "code"),
    ("idx_steps69_code", "steps69_games", "code"),
)


def _partial(where: sa.ColumnElement[bool]) -> dict[str, sa.ColumnElement[bool]]:
    # As the model spells it (models._partial), so both builds agree.
    return {"postgresql_where": where, "sqlite_where": where}


def upgrade() -> None:
    for name, _table, _column in REDUNDANT:
        op.execute(f"DROP INDEX IF EXISTS {name}")

    op.create_index(
        "idx_users_referred_by", "users", ["referred_by"],
        **_partial(sa.column("referred_by").is_not(None)),
    )
    op.create_index("idx_steps69_guest", "steps69_games", ["guest_telegram_user_id"])
    op.create_index(
        "idx_steps69_unfinished_updated", "steps69_games", ["updated_at"],
        **_partial(sa.column("finished").is_(False)),
    )
    op.create_index("idx_compat_creator", "compat_tests", ["creator_telegram_user_id"])
    op.create_index("idx_compat_guest", "compat_tests", ["guest_telegram_user_id"])
    op.create_index(
        "idx_compat_unfinished_updated", "compat_tests", ["updated_at"],
        **_partial(sa.column("finished_at").is_(None)),
    )


def downgrade() -> None:
    for name, table in (
        ("idx_compat_unfinished_updated", "compat_tests"),
        ("idx_compat_guest", "compat_tests"),
        ("idx_compat_creator", "compat_tests"),
        ("idx_steps69_unfinished_updated", "steps69_games"),
        ("idx_steps69_guest", "steps69_games"),
        ("idx_users_referred_by", "users"),
    ):
        op.drop_index(name, table_name=table)
    for name, table, column in REDUNDANT:
        op.create_index(name, table, [column])
