"""add_frame_dimensions_to_match

Revision ID: c3a1f84d2b90
Revises: 888652ddf0d9
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a1f84d2b90'
down_revision: Union[str, Sequence[str], None] = '888652ddf0d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frame_width',  sa.Integer(), nullable=False, server_default='1920'))
        batch_op.add_column(sa.Column('frame_height', sa.Integer(), nullable=False, server_default='1080'))


def downgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_column('frame_height')
        batch_op.drop_column('frame_width')
