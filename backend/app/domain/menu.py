from __future__ import annotations

from pydantic import BaseModel


class Money(BaseModel):
    """A price value object — amount + ISO 4217 currency."""

    amount: float
    currency: str  # "EUR", "CZK", ...


class ExtractedMenuItem(BaseModel):
    """One line item as read off the menu photo.

    Deliberately shallow — the first AI pass only lists what's printed
    (name, price, any allergen marks). Full dish info comes from the cache
    or the per-dish enrichment pass.
    """

    name: str  # exactly as printed
    price: float | None = None
    currency: str | None = None  # ISO 4217, inferred from the menu
    allergen_hints: list[str] = []  # allergens marked on the menu itself


class MenuExtraction(BaseModel):
    """LLM structured-output target for a whole menu photo."""

    items: list[ExtractedMenuItem]
    # ISO 639-1 of the language the menu is printed in — the vision pass reads
    # it off the photo for free. Stored on the menu and reused wherever the
    # staff's language matters (ask-staff question translations).
    language: str | None = None
