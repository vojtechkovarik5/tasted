from enum import StrEnum

from pydantic import BaseModel, field_validator

# Mirrors User.prefs (JSONB) — the device is the source of truth (MMKV),
# this is the sync payload once the user is logged in. Last-write-wins.


class Language(StrEnum):
    """The user's preferred language for menu explanations.

    A fixed allow-list (unlike currency, which is DB-driven) — the settable
    options are exactly these. This is also the set every dish's translations
    are generated for at enrichment time, so adding a language means
    backfilling stored dishes. Codes are ISO 639-1. English is first so it
    leads the picker and is the default (and the read-time fallback).
    """

    en = "en"
    de = "de"
    fr = "fr"
    es = "es"
    pt = "pt"
    zh = "zh"


# Endonyms (each language in its own script) — the convention for a language
# picker, so a speaker recognizes their own. The app chrome stays English.
LANGUAGE_NAMES: dict[Language, str] = {
    Language.en: "English",
    Language.de: "Deutsch",
    Language.fr: "Français",
    Language.es: "Español",
    Language.pt: "Português",
    Language.zh: "中文",
}


class WatchChip(BaseModel):
    """One chip in the "What I track" list. Order in the list matters.

    Keys reference the trackables catalog: allergens are the fixed EU-14,
    dietary and ingredient keys can also be user-suggested (pending) entries.
    """

    key: str  # "gluten", "vegetarian", "coriander", ...
    kind: str  # "allergen" | "dietary" | "ingredient"
    on: bool = True


class Preferences(BaseModel):
    """User preferences (Profile screen). Works locally without an account."""

    # One ordered list — allergens, diets and tracked ingredients. Picked
    # things show as tags on every menu item and dish.
    watch_list: list[WatchChip] = [
        WatchChip(key="gluten", kind="allergen"),
        WatchChip(key="vegetarian", kind="dietary"),
    ]
    # Which macros to show on cards: "protein" | "fat" | "carbs" | "kcal".
    macros: list[str] = ["protein", "fat"]
    # Badge order on every card: "restrictions" | "macros" | "spice_price".
    section_order: list[str] = ["restrictions", "macros", "spice_price"]
    # ISO 4217 — original menu prices get an approximate conversion to this.
    currency: str = "CZK"
    # Preferred language for menu explanations (see Language). The app itself
    # stays English; this is display-only for now.
    language: Language = Language.en

    @field_validator("language", mode="before")
    @classmethod
    def _fallback_removed_language(cls, value):
        """Prefs stored while a since-removed language was supported (e.g.
        "cs") must not break every read — fall back to English."""
        try:
            return Language(str(value).lower())
        except ValueError:
            return Language.en
