"""scans.updated_at for stuck-processing cleanup

Revision ID: b3f2a9c4d1e7
Revises: 193cb8eb7cf7
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f2a9c4d1e7'
down_revision: Union[str, Sequence[str], None] = '193cb8eb7cf7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Bumped on every scan status change; for `processing` scans it marks when
    # the claim happened, so the cleanup task can find pages stuck mid-work.
    op.add_column(
        'scans',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scans', 'updated_at')
