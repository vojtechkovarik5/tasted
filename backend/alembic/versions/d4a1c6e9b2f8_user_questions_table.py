"""user_questions table (saved ask-the-staff questions)

Revision ID: d4a1c6e9b2f8
Revises: b3f2a9c4d1e7
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a1c6e9b2f8'
down_revision: Union[str, Sequence[str], None] = 'b3f2a9c4d1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Saved "Ask the staff" questions, written once in the user's own
    # language, kept in list order (position). See app/models/question.py.
    op.create_table('user_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('text', sa.String(length=500), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_questions_user_id'), 'user_questions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_questions_user_id'), table_name='user_questions')
    op.drop_table('user_questions')
