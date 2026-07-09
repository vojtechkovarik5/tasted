from enum import StrEnum

from pydantic import BaseModel

# Mirrors User.prefs (JSONB) — the device is the source of truth (MMKV),
# this is the sync payload once the user is logged in. Last-write-wins.


class Language(StrEnum):
    """The user's preferred language for menu explanations.

    A fixed allow-list (unlike currency, which is DB-driven) — the settable
    options are exactly these. The app chrome stays English for now; this is
    stored to drive localized dish notes later. MVP just captures the choice.
    Codes are ISO 639-1. English is first so it leads the picker and is the
    default.
    """

    en = "en"
    de = "de"
    fr = "fr"
    es = "es"
    it = "it"
    pt = "pt"
    nl = "nl"
    pl = "pl"
    cs = "cs"
    ja = "ja"
    zh = "zh"
    ko = "ko"


# English display names for the picker (kept English on purpose — see above).
LANGUAGE_NAMES: dict[Language, str] = {
    Language.en: "English",
    Language.de: "German",
    Language.fr: "French",
    Language.es: "Spanish",
    Language.it: "Italian",
    Language.pt: "Portuguese",
    Language.nl: "Dutch",
    Language.pl: "Polish",
    Language.cs: "Czech",
    Language.ja: "Japanese",
    Language.zh: "Chinese",
    Language.ko: "Korean",
}


class WatchChip(BaseModel):
    """One chip in the "Watch out for" list. Order in the list matters."""

    key: str  # "gluten", "vegetarian", "pork", ...
    kind: str  # "allergen" | "dietary"
    on: bool = True


class Preferences(BaseModel):
    """User preferences (Profile screen). Works locally without an account."""

    # One ordered list — allergens, diets, whole categories or exact meats.
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
