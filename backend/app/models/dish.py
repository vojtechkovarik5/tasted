from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import EMBEDDING_DIM, Base

if TYPE_CHECKING:
    from app.models.attribute import DishAttribute


class Dish(Base):
    """A canonical dish in the growing knowledge cache.

    On a menu scan we embed each extracted dish name and vector-search this
    table; a hit returns the stored `data` instantly, a miss triggers an LLM
    enrichment call whose result is stored here (live ingest).
    """

    __tablename__ = "dishes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    region: Mapped[str | None] = mapped_column(String(255))
    # Descriptive payload: description, aliases, translated name, origin...
    # Scored attributes (allergens, dietary, spice, price) live in
    # dish_attributes so they can be voted on and recalculated.
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

    # TODO: add an HNSW ANN index on name_embedding once the table grows
    # (exact search is fine at low volume):
    #   CREATE INDEX ON dishes USING hnsw (name_embedding vector_cosine_ops);


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
