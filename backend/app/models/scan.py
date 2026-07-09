from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.dish import Dish


class Menu(Base):
    """One restaurant menu — the batch a user's scans belong to.

    A menu can span several photos (pages), each of which is one `Scan`.
    "Scan history" in the profile points here, not at individual scans, and
    the user can label the batch with the restaurant's name/description.
    Listing a menu's items means combining the items of all its scans.
    """

    __tablename__ = "menus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable: scanning works logged out; history is only kept for accounts.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(255))  # restaurant name
    description: Mapped[str | None] = mapped_column(Text)
    # ISO 639-1 the menu is printed in, read off the photo during extraction
    # (first page wins). Drives ask-staff question translations. Null for
    # menus scanned before this existed or when the AI couldn't tell.
    language: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    scans: Mapped[list[Scan]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by="Scan.created_at",
        lazy="selectin",
    )


class Scan(Base):
    """One scanned menu photo (a single page) and its resolution progress.

    Persisted so the client can poll while items are still being enriched.
    `image_sha256` doubles as the whole-photo cache key: re-scanning the same
    photo (or the same laminated menu) can reuse a previous extraction.
    """

    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"), index=True
    )
    # new        -> uploaded, waiting for a worker to pick it up
    # processing -> a worker has claimed it (new -> processing is atomic, so two
    #               workers never process the same scan)
    # complete   -> done (or failed page); never re-processed
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | processing | complete
    # Where the uploaded photo is stored (settings.upload_dir), for the
    # background processor and future reprocessing.
    image_path: Mapped[str] = mapped_column(Text)
    image_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Bumped on every status change; for `processing` scans this marks when the
    # claim happened, so the cleanup task can find pages stuck mid-processing.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Failed processing runs so far. A transient failure reverts the scan to
    # `new` and reschedules it; past settings.menu_processing_max_attempts we
    # give up (mark complete) so a permanently-bad photo can't loop forever.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    menu: Mapped[Menu] = relationship(back_populates="scans")
    items: Mapped[list[ScanItem]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        order_by="ScanItem.position",
        lazy="selectin",
    )


class ScanItem(Base):
    """One line item recognized on a scanned menu page.

    Resolution flow per item: embed `original_name` -> vector-search `dishes`
    -> hit links `dish_id` immediately (status=ready); miss stays `pending`
    while the LLM enriches it, then the new dish is ingested and linked.
    """

    __tablename__ = "scan_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)  # order on the page, drives "1 of 12" paging
    original_name: Mapped[str] = mapped_column(String(255))  # exactly as printed
    status: Mapped[str] = mapped_column(String(16), default="pending")  # ready | pending | failed
    # Price as printed on the menu; conversion to the user's currency happens at read time.
    menu_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    menu_price_currency: Mapped[str | None] = mapped_column(String(3))  # ISO 4217
    # "born in Porto, you're in the right city"
    regional_note: Mapped[str | None] = mapped_column(Text)
    # SET NULL: deleting a canonical dish must not tear scan history apart.
    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dishes.id", ondelete="SET NULL"), index=True
    )

    scan: Mapped[Scan] = relationship(back_populates="items")
    dish: Mapped[Dish | None] = relationship(lazy="selectin")
