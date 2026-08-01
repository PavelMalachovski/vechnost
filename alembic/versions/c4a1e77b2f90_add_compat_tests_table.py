"""add_compat_tests_table

Revision ID: c4a1e77b2f90
Revises: b7e2f81c93d4
Create Date: 2026-08-01 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c4a1e77b2f90'
down_revision: str | None = 'b7e2f81c93d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'compat_tests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('creator_telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('creator_name', sa.String(), nullable=True),
        sa.Column('guest_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('guest_name', sa.String(), nullable=True),
        sa.Column('creator_answers', sa.Text(), nullable=False),
        sa.Column('guest_answers', sa.Text(), nullable=False),
        sa.Column('pair_key', sa.String(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('idx_compat_code', 'compat_tests', ['code'])
    op.create_index('idx_compat_pair', 'compat_tests', ['pair_key'])


def downgrade() -> None:
    op.drop_index('idx_compat_pair', table_name='compat_tests')
    op.drop_index('idx_compat_code', table_name='compat_tests')
    op.drop_table('compat_tests')
