"""A refunded gift revokes its certificate.

`certificates.revoked_at` is set when the purchase a gift certificate was
issued for is refunded or charged back. The refund used to fall through to
the buyer's own subscriptions and close them, while the gift code stayed
good for life (backend audit B-06). A revoked certificate cannot be
redeemed and grants no access, redeemed or not.

Deploys run `create_all`; `payments/database.py::_ensure_payment_columns`
adds the column at startup. This revision is for a database managed by
alembic.

Revision ID: d7f2b4c6e8a0
Revises: c3e5a7f9b1d2
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "d7f2b4c6e8a0"
down_revision: str | None = "c3e5a7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("certificates") as batch:
        batch.add_column(sa.Column("revoked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("certificates") as batch:
        batch.drop_column("revoked_at")
