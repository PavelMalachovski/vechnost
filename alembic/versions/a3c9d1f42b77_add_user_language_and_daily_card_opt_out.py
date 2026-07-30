"""add_user_language_and_daily_card_opt_out

Revision ID: a3c9d1f42b77
Revises: 69fc4bb29a08
Create Date: 2026-07-30 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9d1f42b77'
down_revision: Union[str, None] = '69fc4bb29a08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('language', sa.String(), nullable=True))
    op.add_column(
        'users',
        sa.Column(
            'daily_card_opt_out',
            sa.Boolean(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'daily_card_opt_out')
    op.drop_column('users', 'language')
