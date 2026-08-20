"""add_half_time_to_match

Revision ID: a4c7e912b6d3
Revises: f7b2c9d4e310
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c7e912b6d3'
down_revision: Union[str, Sequence[str], None] = 'f7b2c9d4e310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        # Nullable with no server default: NULL is the meaningful "not stated"
        # value, and every existing row genuinely has not stated it.
        batch_op.add_column(sa.Column('half_time_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_column('half_time_seconds')
