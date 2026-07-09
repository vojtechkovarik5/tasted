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


# Endonyms (each language in its own script) — the convention for a language
# picker, so a speaker recognizes their own. The app chrome stays English.
LANGUAGE_NAMES: dict[Language, str] = {
    Language.en: "English",
    Language.de: "Deutsch",
    Language.fr: "Français",
    Language.es: "Español",
    Language.it: "Italiano",
    Language.pt: "Português",
    Language.nl: "Nederlands",
    Language.pl: "Polski",
    Language.cs: "Čeština",
    Language.ja: "日本語",
    Language.zh: "中文",
    Language.ko: "한국어",
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
