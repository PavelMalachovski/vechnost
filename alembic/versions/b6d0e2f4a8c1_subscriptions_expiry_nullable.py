"""A subscription may have no expiry: that is what a lifetime purchase is.

The first revision declared `subscriptions.expires_at` NOT NULL, while the
model - and `user_has_access` - read a NULL expiry as "forever". On a
database built by `alembic upgrade head`, every lifetime grant therefore
failed its INSERT, and the webhook handler reported the failure to Tribute
as a duplicate delivery. Deploys that run `create_all` never had the
constraint; `payments/database.py::_match_model_nullability` releases it at
startup on a database that does.

Revision ID: b6d0e2f4a8c1
Revises: a9c1d2e3f4b5
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "b6d0e2f4a8c1"
down_revision: str | None = "a9c1d2e3f4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.alter_column("expires_at", existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    # Not restored: NOT NULL here only ever rejected lifetime purchases.
    pass
