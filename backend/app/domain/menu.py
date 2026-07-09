from __future__ import annotations

import re

from pydantic import BaseModel, model_validator


class Money(BaseModel):
    """A price value object — amount + ISO 4217 currency."""

    amount: float
    currency: str  # "EUR", "CZK", ...


class ExtractedGroup(BaseModel):
    """One menu section ("Bún", "Soups", "Drinks"), in menu order.

    `name` is the header in the menu's own language only — a bilingual header
    ("GÓI CUỐN - SPRING ROLLS") keeps just the original ("Gói Cuốn").
    `translated_name` is the scanning user's language.
    """

    name: str
    translated_name: str | None = None


class ExtractedMenuItem(BaseModel):
    """One line item as read off the menu photo.

    Deliberately shallow — the first AI pass only lists what's printed
    (name, description, price, allergen marks) plus a translation into the
    scanning user's language. Full canonical dish info comes from the cache
    or the per-dish enrichment pass.
    """

    name: str  # menu's own language only, inline translations + numbering stripped
    # List number/code printed before the name ("5", "A12") — kept separately
    # so ordering by number still works while `name` stays canonical.
    number: str | None = None
    # The name in the user's language — only when translating is meaningful
    # ("Kachna s bramborem" -> "Duck with potatoes"); proper dish names
    # (Francesinha, Phở) stay null.
    translated_name: str | None = None
    # Ingredients/description text printed under the dish, verbatim.
    description: str | None = None
    translated_description: str | None = None  # user's language
    group: str | None = None  # `name` of the ExtractedGroup it appears under
    price: float | None = None
    currency: str | None = None  # ISO 4217, inferred from the menu
    allergen_hints: list[str] = []  # allergens marked on the menu itself

    # "12. Bún Chạo Tôm" / "A3) ..." / "7 - ..." — the printed list code.
    _NUMBER_PREFIX = re.compile(r"^\s*(?P<num>\d{1,3}[a-zA-Z]?|[A-Z]\d{1,3})\s*[.):\-]\s+")

    @model_validator(mode="after")
    def _normalize(self) -> ExtractedMenuItem:
        """Deterministic cleanup of what the prompt asks for but the model
        occasionally misses: numbering stripped out of `name` (it would
        pollute the canonical dish cache) and translations that merely echo
        the original dropped to null."""
        match = self._NUMBER_PREFIX.match(self.name)
        if match and self.name[match.end():].strip():
            self.name = self.name[match.end():].strip()
            self.number = self.number or match.group("num")
        if self.translated_name:
            match = self._NUMBER_PREFIX.match(self.translated_name)
            if match and self.translated_name[match.end():].strip():
                self.translated_name = self.translated_name[match.end():].strip()
        if self.translated_name and self.translated_name.strip() == self.name.strip():
            self.translated_name = None
        if (
            self.translated_description
            and self.description
            and self.translated_description.strip() == self.description.strip()
        ):
            self.translated_description = None
        return self


class MenuExtraction(BaseModel):
    """LLM structured-output target for a whole menu photo."""

    items: list[ExtractedMenuItem]
    # Section headers in menu order; items reference them via `group`.
    groups: list[ExtractedGroup] = []
    # ISO 639-1 of the language the menu is printed in — the vision pass reads
    # it off the photo for free. Stored on the menu and reused wherever the
    # staff's language matters (ask-staff question translations).
    language: str | None = None
