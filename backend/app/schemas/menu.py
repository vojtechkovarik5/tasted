from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel

from app.domain.menu import Money
from app.schemas.dish import DishOut


class MenuItemStatus(StrEnum):
    """Per-item resolution state — this is what makes loading async.

    ready   -> dish was found in the DB cache; `dish` is populated
    pending -> dish is being enriched by the AI right now; `dish` is null,
               poll GET /menus/{id} until it flips to ready
    failed  -> enrichment failed; show the original name only
    """

    ready = "ready"
    pending = "pending"
    failed = "failed"


class MenuStatus(StrEnum):
    processing = "processing"  # at least one item still pending
    complete = "complete"  # every item is ready or failed


class MenuItemOut(BaseModel):
    """One line item recognized on the menu (across all its photo pages)."""

    id: uuid.UUID
    original_name: str  # exactly as printed
    status: MenuItemStatus
    menu_price: Money | None = None  # as printed on the menu
    approx_price: Money | None = None  # converted to the user's currency
    regional_note: str | None = None  # "born in Porto, you're in the right city"
    dish: DishOut | None = None  # null while status == pending


class MenuOut(BaseModel):
    """Response of POST /menus and GET /menus/{id}.

    One menu = one restaurant visit, possibly several photos (pages);
    `items` is the flattened list across pages. The client renders `ready`
    items immediately and polls while status == processing.
    """

    id: uuid.UUID
    name: str | None = None  # restaurant name (user-editable later)
    status: MenuStatus
    created_at: str  # ISO 8601
    # ISO 639-1 the menu is printed in (read during extraction). The ask-staff
    # sheet passes it to POST /questions/translate as the target language.
    language: str | None = None
    items: list[MenuItemOut]


class MenuSummaryOut(BaseModel):
    """One row of the user's menu history (GET /menus)."""

    id: uuid.UUID
    name: str | None = None
    status: MenuStatus
    created_at: str  # ISO 8601
    item_count: int
