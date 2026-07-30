"""add_rooms_table

Revision ID: b7e2f81c93d4
Revises: a3c9d1f42b77
Create Date: 2026-07-30 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f81c93d4'
down_revision: Union[str, None] = 'a3c9d1f42b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rooms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('creator_telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('creator_name', sa.String(), nullable=True),
        sa.Column('guest_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('guest_name', sa.String(), nullable=True),
        sa.Column('theme', sa.String(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(), nullable=False, server_default='questions'),
        sa.Column('card_order', sa.Text(), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('turn', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('finished', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('idx_room_code', 'rooms', ['code'])


def downgrade() -> None:
    op.drop_index('idx_room_code', table_name='rooms')
    op.drop_table('rooms')
