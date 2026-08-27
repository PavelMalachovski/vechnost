"""steps69: one piece per player instead of one per couple

Revision ID: e1c7a94d3b28
Revises: d8f3b2a51c60
Create Date: 2026-08-27

Every position, roll count and Joker becomes two, and the shared emoji
reactions go away with the feature. Unfinished games are not migrated: a
single position cannot be split into two without inventing where the second
partner stood, so both pieces start again from cell 1.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1c7a94d3b28'
down_revision: str | None = 'd8f3b2a51c60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('steps69_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creator_position', sa.Integer(),
                                      nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('guest_position', sa.Integer(),
                                      nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('creator_piece', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('guest_piece', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('creator_turns', sa.Integer(),
                                      nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('guest_turns', sa.Integer(),
                                      nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('creator_joker_task_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('guest_joker_task_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('last_seat', sa.Integer(), nullable=True))
        batch_op.drop_column('position')
        batch_op.drop_column('turns')
        batch_op.drop_column('joker_task_id')
        batch_op.drop_column('reactions')


def downgrade() -> None:
    with op.batch_alter_table('steps69_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position', sa.Integer(),
                                      nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('turns', sa.Integer(),
                                      nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('joker_task_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('reactions', sa.Text(),
                                      nullable=False, server_default='[]'))
        batch_op.drop_column('last_seat')
        batch_op.drop_column('guest_joker_task_id')
        batch_op.drop_column('creator_joker_task_id')
        batch_op.drop_column('guest_turns')
        batch_op.drop_column('creator_turns')
        batch_op.drop_column('guest_piece')
        batch_op.drop_column('creator_piece')
        batch_op.drop_column('guest_position')
        batch_op.drop_column('creator_position')
