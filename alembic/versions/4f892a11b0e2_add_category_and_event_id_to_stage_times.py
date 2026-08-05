"""add category and event_id to stage_times

Revision ID: 4f892a11b0e2
Revises: 35052ecbe6cf
Create Date: 2026-08-06 00:04:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f892a11b0e2'
down_revision: Union[str, Sequence[str], None] = '35052ecbe6cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add category and event_id columns to stage_times table."""
    op.add_column('stage_times', sa.Column('category', sa.String(), nullable=True))
    op.add_column('stage_times', sa.Column('event_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_stage_times_category'), 'stage_times', ['category'], unique=False)
    op.create_index(op.f('ix_stage_times_event_id'), 'stage_times', ['event_id'], unique=False)


def downgrade() -> None:
    """Remove category and event_id columns from stage_times table."""
    op.drop_index(op.f('ix_stage_times_event_id'), table_name='stage_times')
    op.drop_index(op.f('ix_stage_times_category'), table_name='stage_times')
    op.drop_column('stage_times', 'event_id')
    op.drop_column('stage_times', 'category')
