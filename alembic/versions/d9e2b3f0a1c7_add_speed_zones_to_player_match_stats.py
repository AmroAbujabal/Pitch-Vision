"""add_speed_zones_to_player_match_stats

Revision ID: d9e2b3f0a1c7
Revises: c3a1f84d2b90
Create Date: 2026-06-24 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e2b3f0a1c7'
down_revision: Union[str, Sequence[str], None] = 'c3a1f84d2b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('player_match_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('speed_zones', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('player_match_stats', schema=None) as batch_op:
        batch_op.drop_column('speed_zones')
