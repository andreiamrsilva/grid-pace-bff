"""add spectator_zones_json to event_briefings

Revision ID: 5a1b2c3d4e5f
Revises: 4f892a11b0e2
Create Date: 2026-08-07 19:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '4f892a11b0e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add spectator_zones_json column to event_briefings table."""
    op.add_column('event_briefings', sa.Column('spectator_zones_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove spectator_zones_json column from event_briefings table."""
    op.drop_column('event_briefings', 'spectator_zones_json')
