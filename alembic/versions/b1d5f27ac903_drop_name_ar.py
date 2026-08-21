"""drop_name_ar

Removes the Arabic-name columns from academies and players.

The product is English-only for a Canadian market, so a column reserved for one
specific script is a preference the schema should not carry. Nothing read these
columns — they were written through `PlayerBase` and returned again, never used
for search, display or matching — so dropping them loses no behaviour.

If a club ever needs an alternate name, add a script-neutral column then. Adding
`name_ar` back is what `downgrade` is for; it restores the column but not the
data, which is unrecoverable once dropped.

Revision ID: b1d5f27ac903
Revises: a4c7e912b6d3
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1d5f27ac903'
down_revision: Union[str, Sequence[str], None] = 'a4c7e912b6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('name_ar')
    with op.batch_alter_table('academies', schema=None) as batch_op:
        batch_op.drop_column('name_ar')


def downgrade() -> None:
    # Nullable on the way back because the dropped values are gone — there is
    # nothing to backfill an existing row with.
    with op.batch_alter_table('academies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_ar', sa.String(length=200), nullable=True))
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_ar', sa.String(length=200), nullable=True))
