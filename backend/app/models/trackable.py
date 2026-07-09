from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Trackable(Base):
    """One entry of the "What I track" catalog — an allergen, a diet flag or
    an ingredient users can pick in settings and see as tags everywhere.

    Allergens are the fixed EU-14 (seeded by migration, never suggestable).
    Diet flags and ingredients grow two ways: the AI enrichment pipeline
    upserts ingredients it encounters (status=active), and users can suggest
    new entries (status=pending) — a later AI moderation task will decide
    whether a pending entry graduates; for now it just sits there, visible
    only to its suggester.

    `translations` maps ISO 639-1 -> {"name": ..., "description": ...};
    anything missing falls back to the English `name`/`description` columns.
    """

    __tablename__ = "trackables"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('allergen', 'dietary', 'ingredient')", name="ck_trackables_kind"
        ),
        CheckConstraint("status IN ('active', 'pending')", name="ck_trackables_status"),
        Index("uq_trackables_kind_key", "kind", "key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16))  # allergen | dietary | ingredient
    key: Mapped[str] = mapped_column(String(64))  # canonical slug: "gluten", "rice-noodles"
    name: Mapped[str] = mapped_column(String(255))  # English display name
    description: Mapped[str | None] = mapped_column(Text)  # what the user wrote when suggesting
    translations: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | pending
    # Who suggested a pending entry; null for seeded/AI-created ones.
    suggested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
