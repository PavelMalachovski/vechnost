"""A Tribute event is processed once, and a gift purchase mints one certificate.

`webhook_events.event_key` holds a hash of what makes two deliveries one
event (see `TributeEvent.idempotency_key`): Tribute stamps each attempt
with its own `sent_at`, so a redelivery never matched the body hash it was
checked against, and a redelivered gift purchase minted another lifetime
certificate (backend audit B-07). `certificates.purchase_id` links a gift
certificate to the purchase that paid for it. Both are unique where set.

Deploys run `create_all`, which never alters an existing table, so
`payments/database.py::_ensure_payment_columns` adds the same columns and
indexes at startup; this revision is for a database managed by alembic.

Revision ID: c3e5a7f9b1d2
Revises: b6d0e2f4a8c1
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "c3e5a7f9b1d2"
down_revision: str | None = "b6d0e2f4a8c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("webhook_events") as batch:
        batch.add_column(sa.Column("event_key", sa.String(), nullable=True))
    op.create_index("uq_webhook_events_event_key", "webhook_events", ["event_key"], unique=True)
    with op.batch_alter_table("certificates") as batch:
        batch.add_column(sa.Column("purchase_id", sa.String(), nullable=True))
    op.create_index("uq_certificates_purchase_id", "certificates", ["purchase_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_certificates_purchase_id", table_name="certificates")
    with op.batch_alter_table("certificates") as batch:
        batch.drop_column("purchase_id")
    op.drop_index("uq_webhook_events_event_key", table_name="webhook_events")
    with op.batch_alter_table("webhook_events") as batch:
        batch.drop_column("event_key")
