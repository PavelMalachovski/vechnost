"""users: a referral code to hand out and a record of who invited whom

Revision ID: f2b8c05e71a4
Revises: e1c7a94d3b28
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2b8c05e71a4'
down_revision: str | None = 'e1c7a94d3b28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referral_code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('referred_by', sa.BigInteger(), nullable=True))
        batch_op.create_unique_constraint('uq_users_referral_code', ['referral_code'])
        batch_op.create_index('idx_referral_code', ['referral_code'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('idx_referral_code')
        batch_op.drop_constraint('uq_users_referral_code', type_='unique')
        batch_op.drop_column('referred_by')
        batch_op.drop_column('referral_code')
