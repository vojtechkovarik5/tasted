from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel

from app.domain.menu import Money
from app.schemas.dish import DishOut


class MenuItemStatus(StrEnum):
    """Per-item resolution state — this is what makes loading async.

    ready   -> resolution finished. `dish` MAY be populated (a matched
               canonical family, with `match_confidence`) or null — a menu
               item doesn't need a match; it then "stays as written".
    pending -> the item is going through cache/enrichment right now; poll
               GET /menus/{id} until it flips to ready
    failed  -> processing failed; show the printed fields only
    """

    ready = "ready"
    pending = "pending"
    failed = "failed"


class MenuStatus(StrEnum):
    processing = "processing"  # at least one item still pending
    complete = "complete"  # every item is ready or failed


class MenuTagOut(BaseModel):
    """One printed ingredient/allergen tag on a menu item card. `key` is the
    canonical trackables slug (null when there is none) so the client can
    match the user's tracked things; `name` is already localized."""

    key: str | None = None
    name: str


class MenuItemOut(BaseModel):
    """One line item recognized on the menu (across all its photo pages).

    The printed fields (`original_name`, `menu_description`, `group_name`)
    mirror the menu; the `*_translated` twins are the scanning user's
    language, made once during extraction. Canonical shared knowledge lives
    under `dish`.
    """

    id: uuid.UUID
    original_name: str  # menu's own language, inline translations stripped
    menu_number: str | None = None  # printed list number/code ("5", "A12")
    translated_name: str | None = None  # user's language, only when meaningful
    menu_description: str | None = None  # ingredients/description as printed
    menu_description_translated: str | None = None
    group_name: str | None = None  # menu section ("Bún", "Drinks")
    group_name_translated: str | None = None
    status: MenuItemStatus
    menu_price: Money | None = None  # as printed on the menu
    approx_price: Money | None = None  # converted to the user's currency
    regional_note: str | None = None  # "born in Porto, you're in the right city"
    # What the menu prints as contents/allergens for this item, localized
    # ("Contains: rice noodles · chicken", "Allergens: peanuts · egg").
    menu_ingredients: list[MenuTagOut] = []
    menu_allergens: list[MenuTagOut] = []
    # The OPTIONAL canonical family match. `dish` is null while pending AND
    # when nothing matched confidently — the item then stays as written.
    dish: DishOut | None = None
    match_confidence: int | None = None  # 0-100, "Pad Thai · 91%"
    matched_variant_key: str | None = None  # highlighted chip on the family page


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
    """One row of the user's menu history (GET /menus):
    "Café Santiago · 2 scans · 12 dishes · 🇵🇹 Portuguese"."""

    id: uuid.UUID
    name: str | None = None
    status: MenuStatus
    created_at: str  # ISO 8601
    item_count: int
    scan_count: int  # photo pages uploaded for this menu
    language: str | None = None  # ISO 639-1 the menu is printed in


class MenuRename(BaseModel):
    """PATCH /menus/{id} body — the pencil next to the name in the list.
    Null/empty clears the name back to "Untitled menu"."""

    name: str | None = None
