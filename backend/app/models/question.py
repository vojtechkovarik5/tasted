from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserQuestion(Base):
    """One saved "Ask the staff" question (Settings -> My questions).

    Written once in the user's own language (Preferences.language) and shown
    on the ask-staff sheet, where it gets translated into the menu's language
    on demand. Translations are cached per target language on the device, so
    the row stays language-agnostic: only the user's original text is stored.
    """

    __tablename__ = "user_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The question exactly as the user wrote it, in their own language.
    text: Mapped[str] = mapped_column(String(500))
    # 0-based order in the list (the sheet shows questions in this order).
    # Reordering rewrites the positions of all the user's rows, so no unique
    # constraint — it would fight the in-place renumbering.
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
