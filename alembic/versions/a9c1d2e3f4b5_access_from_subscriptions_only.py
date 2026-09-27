"""Access is read from subscriptions only; rejected webhooks are forgotten.

Two data moves, no schema change. Both are also applied idempotently at
startup by `payments/database.py`, because deploys run `create_all` rather
than alembic; this revision exists so a database managed by alembic gets
the same treatment once.

1. `user_has_access` used to count any `payments` row without an expiry as
   lifetime access. It now reads `subscriptions` only, so every user whose
   access rested on such a payment gets the equivalent lifetime row.
2. A webhook refused for its signature used to be recorded under the
   body's hash, which made Tribute's correctly signed retry of the same
   body an "already processed" no-op. Those rows are the payments the
   deployment lost; deleting them lets a retry or a redelivery land.

Revision ID: a9c1d2e3f4b5
Revises: f2b8c05e71a4
Create Date: 2026-09-03
"""

from alembic import op

revision: str = "a9c1d2e3f4b5"
down_revision: str | None = "f2b8c05e71a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The NULL is typed: PostgreSQL types a bare NULL in SELECT DISTINCT as
    # text and refuses it for a timestamp, which failed this revision - and,
    # the whole upgrade being one transaction, left no tables at all. The
    # cutover keeps it to payments the old access rule actually counted;
    # see ACCESS_FROM_PAYMENTS_CUTOVER in payments/database.py.
    op.execute(
        "INSERT INTO subscriptions "
        "(user_id, subscription_id, period, status, expires_at, last_event_at) "
        "SELECT DISTINCT p.user_id, 0, 'lifetime', 'active', "
        "CAST(NULL AS TIMESTAMP), CURRENT_TIMESTAMP "
        "FROM payments p "
        "WHERE p.expires_at IS NULL "
        "AND p.created_at < '2026-09-03 16:00:00' "
        "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = p.user_id)"
    )
    # Rejected deliveries keep their rows with the hash renamed, as the
    # startup step does (payments/database.py::_release_stuck_webhooks): the
    # retry is no longer a duplicate, and the row still says which payment
    # to redeliver.
    op.execute(
        "UPDATE webhook_events SET body_sha256 = 'released:' || body_sha256 "
        "WHERE status_code >= 400 AND body_sha256 NOT LIKE 'released:%'"
    )


def downgrade() -> None:
    # Data only. The backfilled rows are indistinguishable from real ones
    # by design, and a released rejection record is better left released;
    # neither is undone.
    pass
