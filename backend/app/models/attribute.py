from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DishAttribute(Base):
    """One scored attribute of a dish — the row behind every bar/badge.

    All attribute kinds share a single 0-100 scale so storage, voting and
    recalculation are uniform; only the rendering differs:
      allergen  "gluten 99%"      — probability the dish contains it
      dietary   "vegetarian 2%"   — probability the dish satisfies the diet
      spice     0-100 -> 0-5 chili icons (value / 20)
      price     0-100 -> 1-5 "€" icons

    `base_value` is the AI's estimate from ingest and never changes; `value`
    is what the app shows. Votes don't touch either directly — the periodic
    recalculation task (tasks.py:recalculate_dish_attributes) recomputes
    `value` from `base_value` + the net votes, so a vote is a voice in the
    next recalc, not an instant nudge.
    """

    __tablename__ = "dish_attributes"
    __table_args__ = (
        CheckConstraint("value BETWEEN 0 AND 100", name="ck_dish_attributes_value_range"),
        CheckConstraint(
            "base_value BETWEEN 0 AND 100", name="ck_dish_attributes_base_value_range"
        ),
        CheckConstraint(
            "(kind IN ('allergen', 'dietary')) = (key IS NOT NULL)",
            name="ck_dish_attributes_key_presence",
        ),
        # One row per attribute. NULLS NOT DISTINCT so the key-less kinds
        # (spice, price) dedupe too.
        Index(
            "uq_dish_attributes_dish_kind_key",
            "dish_id",
            "kind",
            "key",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # allergen | dietary | spice | price
    # Attribute slug for allergen/dietary ("gluten", "vegetarian"); NULL for spice/price.
    key: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[int] = mapped_column(SmallInteger)  # displayed score, 0-100
    # AI baseline from ingest (0-100), immutable — recalculation anchor.
    base_value: Mapped[int] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    votes: Mapped[list[DishVote]] = relationship(
        back_populates="attribute", cascade="all, delete-orphan"
    )


class DishVote(Base):
    """One user's nudge on one dish attribute (the <- / -> arrows in the UI).

    -1 = left arrow (less likely / milder / cheaper), +1 = right arrow.
    One vote per user per attribute — re-voting upserts on the unique
    constraint, so users can change their mind. Raw votes are kept (not a
    running total) so the summary in `dish_attributes.value` can be
    recalculated over any time window.
    """

    __tablename__ = "dish_votes"
    __table_args__ = (
        CheckConstraint("direction IN (-1, 1)", name="ck_dish_votes_direction"),
        Index("uq_dish_votes_attribute_user", "attribute_id", "user_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dish_attributes.id", ondelete="CASCADE"), index=True
    )
    # Voting requires sign-in ("Sign in to vote & sync"), so this is non-null.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    attribute: Mapped[DishAttribute] = relationship(back_populates="votes")
