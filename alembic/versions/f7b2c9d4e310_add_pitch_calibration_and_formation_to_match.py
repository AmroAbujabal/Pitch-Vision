"""add_pitch_calibration_and_formation_to_match

Revision ID: f7b2c9d4e310
Revises: d9e2b3f0a1c7
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2c9d4e310'
down_revision: Union[str, Sequence[str], None] = 'd9e2b3f0a1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pitch_corners',    sa.JSON(),      nullable=True))
        batch_op.add_column(sa.Column('home_defends_end', sa.String(4),   nullable=True))
        batch_op.add_column(sa.Column('home_formation',   sa.String(20),  nullable=True))
        batch_op.add_column(sa.Column('away_formation',   sa.String(20),  nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_column('away_formation')
        batch_op.drop_column('home_formation')
        batch_op.drop_column('home_defends_end')
        batch_op.drop_column('pitch_corners')
