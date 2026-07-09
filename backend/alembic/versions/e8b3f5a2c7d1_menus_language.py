"""menus.language (printed language, read during extraction)

Revision ID: e8b3f5a2c7d1
Revises: d4a1c6e9b2f8
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b3f5a2c7d1'
down_revision: Union[str, Sequence[str], None] = 'd4a1c6e9b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ISO 639-1 the menu is printed in; the extraction pass reads it off the
    # photo. Null for pre-existing menus — see app/models/scan.py.
    op.add_column('menus', sa.Column('language', sa.String(length=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('menus', 'language')
