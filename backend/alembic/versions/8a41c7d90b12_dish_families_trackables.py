"""dish families, variants, trackables catalog, optional menu-item match

- `trackables`: the "What I track" catalog (fixed EU-14 allergens + diet
  flags seeded here; ingredients grow from AI ingest and user suggestions,
  the latter as `pending`).
- `dish_variants`: facets of a dish family ("Gai · chicken"), referencable
  by menu items.
- `scan_items`: a menu item may (not must) match a dish family — adds
  match_confidence, dish_variant_id, plus the printed ingredients/allergens
  faithful to the menu.
- `dish_attributes`: new `ingredient` kind joins the keyed kinds.

Revision ID: 8a41c7d90b12
Revises: 1fcf61e22684
Create Date: 2026-07-09

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a41c7d90b12'
down_revision: Union[str, Sequence[str], None] = '1fcf61e22684'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The fixed catalog seed: (kind, key, english name, czech name). English is
# the fallback for every other language until translations are backfilled.
SEED = [
    ("allergen", "gluten", "gluten", "lepek"),
    ("allergen", "crustaceans", "crustaceans", "korýši"),
    ("allergen", "egg", "egg", "vejce"),
    ("allergen", "fish", "fish", "ryby"),
    ("allergen", "peanuts", "peanuts", "arašídy"),
    ("allergen", "soy", "soy", "sója"),
    ("allergen", "milk", "milk", "mléko"),
    ("allergen", "nuts", "tree nuts", "skořápkové plody"),
    ("allergen", "celery", "celery", "celer"),
    ("allergen", "mustard", "mustard", "hořčice"),
    ("allergen", "sesame", "sesame", "sezam"),
    ("allergen", "sulphites", "sulphites", "siřičitany"),
    ("allergen", "lupin", "lupin", "vlčí bob"),
    ("allergen", "molluscs", "molluscs", "měkkýši"),
    ("dietary", "vegetarian", "vegetarian", "vegetariánské"),
    ("dietary", "vegan", "vegan", "veganské"),
    ("dietary", "meat", "meat", "maso"),
    ("dietary", "fish-seafood", "fish/seafood", "ryby a mořské plody"),
    ("dietary", "raw", "raw", "syrové"),
    ("dietary", "fried", "fried", "smažené"),
    ("dietary", "halal", "halal", "halal"),
    ("dietary", "kosher", "kosher", "košer"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'trackables',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('translations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('suggested_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('allergen', 'dietary', 'ingredient')", name='ck_trackables_kind'),
        sa.CheckConstraint("status IN ('active', 'pending')", name='ck_trackables_status'),
        sa.ForeignKeyConstraint(['suggested_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trackables_suggested_by'), 'trackables', ['suggested_by'], unique=False)
    op.create_index('uq_trackables_kind_key', 'trackables', ['kind', 'key'], unique=True)

    op.create_table(
        'dish_variants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('dish_id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('translations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dish_id'], ['dishes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dish_variants_dish_id'), 'dish_variants', ['dish_id'], unique=False)
    op.create_index('uq_dish_variants_dish_key', 'dish_variants', ['dish_id', 'key'], unique=True)

    op.add_column('scan_items', sa.Column('menu_ingredients', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('scan_items', sa.Column('menu_allergens', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('scan_items', sa.Column('match_confidence', sa.SmallInteger(), nullable=True))
    op.add_column('scan_items', sa.Column('dish_variant_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_scan_items_dish_variant_id'), 'scan_items', ['dish_variant_id'], unique=False)
    op.create_foreign_key(
        'fk_scan_items_dish_variant_id',
        'scan_items',
        'dish_variants',
        ['dish_variant_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # `ingredient` joins the keyed attribute kinds.
    op.drop_constraint('ck_dish_attributes_key_presence', 'dish_attributes', type_='check')
    op.create_check_constraint(
        'ck_dish_attributes_key_presence',
        'dish_attributes',
        "(kind IN ('allergen', 'dietary', 'ingredient')) = (key IS NOT NULL)",
    )

    trackables = sa.table(
        'trackables',
        sa.column('id', sa.UUID()),
        sa.column('kind', sa.String()),
        sa.column('key', sa.String()),
        sa.column('name', sa.String()),
        sa.column('translations', postgresql.JSONB()),
        sa.column('status', sa.String()),
    )
    op.bulk_insert(
        trackables,
        [
            {
                'id': str(uuid.uuid4()),
                'kind': kind,
                'key': key,
                'name': name_en,
                'translations': {'cs': {'name': name_cs}},
                'status': 'active',
            }
            for kind, key, name_en, name_cs in SEED
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_dish_attributes_key_presence', 'dish_attributes', type_='check')
    op.create_check_constraint(
        'ck_dish_attributes_key_presence',
        'dish_attributes',
        "(kind IN ('allergen', 'dietary')) = (key IS NOT NULL)",
    )
    op.drop_constraint('fk_scan_items_dish_variant_id', 'scan_items', type_='foreignkey')
    op.drop_index(op.f('ix_scan_items_dish_variant_id'), table_name='scan_items')
    op.drop_column('scan_items', 'dish_variant_id')
    op.drop_column('scan_items', 'match_confidence')
    op.drop_column('scan_items', 'menu_allergens')
    op.drop_column('scan_items', 'menu_ingredients')
    op.drop_index('uq_dish_variants_dish_key', table_name='dish_variants')
    op.drop_index(op.f('ix_dish_variants_dish_id'), table_name='dish_variants')
    op.drop_table('dish_variants')
    op.drop_index('uq_trackables_kind_key', table_name='trackables')
    op.drop_index(op.f('ix_trackables_suggested_by'), table_name='trackables')
    op.drop_table('trackables')
