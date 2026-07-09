from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import EMBEDDING_DIM, Base

if TYPE_CHECKING:
    from app.models.attribute import DishAttribute


class Dish(Base):
    """One canonical dish FAMILY in the growing knowledge cache.

    One row per family — thousands of menu variants collapse into facets
    (DishVariant rows); combos (lomo saltado, loaded fries) are one family
    too, never split. On a menu scan we embed each extracted item name and
    vector-search this table; a hit links the family (with a confidence
    score), a miss triggers an LLM enrichment call whose result is stored
    here (live ingest).

    `data` is the DishInfo payload, including `translations` — the stored
    per-language versions of the prose, falling back to English at read time.
    """

    __tablename__ = "dishes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    region: Mapped[str | None] = mapped_column(String(255))
    # Descriptive payload: description, aliases, pronunciation, category,
    # similar dishes, per-language translations... Scored attributes
    # (allergens, dietary, ingredients, spice, price) live in dish_attributes
    # so they can be voted on and recalculated.
    data: Mapped[dict] = mapped_column(JSONB)
    name_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    photos: Mapped[list[DishPhoto]] = relationship(
        back_populates="dish", cascade="all, delete-orphan", lazy="selectin"
    )
    attributes: Mapped[list[DishAttribute]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    variants: Mapped[list[DishVariant]] = relationship(
        back_populates="dish",
        cascade="all, delete-orphan",
        order_by="DishVariant.position",
        lazy="selectin",
    )

    # TODO: add an HNSW ANN index on name_embedding once the table grows
    # (exact search is fine at low volume):
    #   CREATE INDEX ON dishes USING hnsw (name_embedding vector_cosine_ops);


class DishVariant(Base):
    """One common variant (facet) of a dish family — "Gai · chicken" on the
    Pad Thai page.

    Variants are facets, not separate canonical pages; menu items may link
    the one they matched (scan_items.dish_variant_id) so the family page can
    highlight it. `translations` holds per-language display names/descriptions
    ({lang: {"name": ..., "description": ...}}), falling back to English.
    """

    __tablename__ = "dish_variants"
    __table_args__ = (
        Index("uq_dish_variants_dish_key", "dish_id", "key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64))  # slug within the family: "gai"
    name: Mapped[str] = mapped_column(String(255))  # "Gai · chicken"
    description: Mapped[str | None] = mapped_column(Text)
    translations: Mapped[dict] = mapped_column(JSONB, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)

    dish: Mapped[Dish] = relationship(back_populates="variants")


class DishPhoto(Base):
    """A photo for a dish. Resolved by priority: user > ai."""

    __tablename__ = "dish_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)  # points at our own object storage, never a hotlink
    source: Mapped[str] = mapped_column(String(32))  # user | ai
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | pending_moderation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    dish: Mapped[Dish] = relationship(back_populates="photos")
