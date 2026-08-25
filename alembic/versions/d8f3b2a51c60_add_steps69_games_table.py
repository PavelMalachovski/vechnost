"""add steps69_games table

Revision ID: d8f3b2a51c60
Revises: c4a1e77b2f90
Create Date: 2026-08-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8f3b2a51c60'
down_revision: str | None = 'c4a1e77b2f90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'steps69_games',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False, server_default='duo'),
        sa.Column('creator_telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('creator_name', sa.String(), nullable=True),
        sa.Column('guest_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('guest_name', sa.String(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('turn', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('turns', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_roll', sa.Integer(), nullable=True),
        sa.Column('last_from', sa.Integer(), nullable=True),
        sa.Column('last_landed', sa.Integer(), nullable=True),
        sa.Column('last_event', sa.String(), nullable=True),
        sa.Column('joker_task_id', sa.String(), nullable=True),
        sa.Column('used_jokers', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('reactions', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('finale_choice', sa.String(), nullable=True),
        sa.Column('finished', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('resume_notified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    with op.batch_alter_table('steps69_games', schema=None) as batch_op:
        batch_op.create_index('idx_steps69_code', ['code'], unique=False)
        batch_op.create_index(
            'idx_steps69_creator', ['creator_telegram_user_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('steps69_games', schema=None) as batch_op:
        batch_op.drop_index('idx_steps69_creator')
        batch_op.drop_index('idx_steps69_code')

    op.drop_table('steps69_games')
