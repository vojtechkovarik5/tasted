from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """An authenticated user. Identity is owned by Clerk.

    Clerk handles the Apple/Google sign-in flows; the API just verifies the
    session JWT and keys rows by its stable `sub` claim (`clerk_user_id`).
    Rows are created lazily on first authenticated request. Email and name
    are convenience mirrors of the Clerk profile, not sources of truth.

    The app is fully usable logged out — preferences live in MMKV on the
    device. Logging in is only needed to vote and to sync `prefs` across
    devices, so this table stays minimal.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255))
    # Mirror of the device prefs (schemas.Preferences), last-write-wins:
    # watch_list, macros, section_order, currency.
    prefs: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
