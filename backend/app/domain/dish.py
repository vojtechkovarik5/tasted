from __future__ import annotations

from pydantic import BaseModel, Field


class Allergen(BaseModel):
    """Probability that a typical version of the dish contains the allergen.

    `name` is the canonical slug of one of the 14 EU allergens ("gluten",
    "peanuts", "crustaceans", ...) — display names come from the trackables
    catalog, localized to the user's language.
    """

    name: str  # canonical slug: "gluten", "egg", "milk", "peanuts", ...
    probability: float = Field(ge=0, le=1)  # rendered as "gluten 99%"
    # Localized display name, filled at the API edge from the trackables
    # catalog (user's language, English fallback). Never stored.
    label: str | None = None


class DietaryFlag(BaseModel):
    """Share of versions of the dish worldwide that fit a diet facet.

    "vegetarian 0.35" -> about a third of versions are vegetarian; the UI
    renders it as "vegetarian 35%" in the dish's Diet fit section, or as a
    conflict on cards when the user tracks that diet and the share is low.
    """

    name: str  # canonical slug: "vegetarian", "vegan", "raw", "fried", ...
    probability: float = Field(ge=0, le=1)
    label: str | None = None  # localized at the API edge, never stored


class Ingredient(BaseModel):
    """Probability that a typical version of the dish contains the ingredient.

    `name` is a canonical English slug ("rice-noodles", "tamarind"); display
    names come from the trackables catalog, localized to the user's language.
    """

    name: str
    probability: float = Field(ge=0, le=1)
    label: str | None = None  # localized at the API edge, never stored


class Macros(BaseModel):
    """Whole-dish average macros per 100 g across variants — an AI estimate,
    shown in the dish detail and (selected ones) as tags on cards."""

    kcal: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)


class DishVariantInfo(BaseModel):
    """One common variant (facet) of a dish family — "Gai · chicken" on the
    Pad Thai page. Variants are facets of the family page, never separate
    canonical dishes; menu items may point at the one they matched."""

    key: str  # slug within the family: "gai", "goong", "jay"
    name: str  # display name: "Gai · chicken"
    description: str | None = None


class DishTranslation(BaseModel):
    """The dish's textual fields in one language. Anything missing falls back
    to the canonical English text at read time.

    A LIST entry (with an explicit `language`), not a dict keyed by language —
    OpenAI's strict structured-output schema rejects free-form dict keys.
    """

    language: str  # ISO 639-1: "cs", "de", ...
    summary: str | None = None
    description: str | None = None


class NameTranslation(BaseModel):
    """One localized display name (for catalog entries)."""

    language: str  # ISO 639-1
    name: str


class IngredientEntry(BaseModel):
    """Enrichment output row for one common ingredient: canonical slug,
    probability, English name and per-language translations. The translations
    are upserted into the trackables catalog so every surface (tags, dish
    detail, settings search) shows the same localized name."""

    key: str  # canonical slug: "rice-noodles"
    name: str  # English display name: "rice noodles"
    probability: float = Field(ge=0, le=1)
    translations: list[NameTranslation] = []


class DishInfo(BaseModel):
    """Canonical knowledge about one dish FAMILY — the core domain model.

    One family page per dish: thousands of menu variants collapse into facets
    (`variants`, e.g. noodle x protein); combos are one family too. Doubles as
    the JSON payload stored in `Dish.data` — except the scored fields
    (allergens, dietary, ingredients, spice_level, price_level), which are
    persisted as `dish_attributes` rows so they can be voted on, and merged
    back in by the read path.

    All prose is canonical English; `translations` holds the stored
    per-language versions (missing languages fall back to English).
    """

    original_name: str  # canonical family name ("Pad Thai")
    aliases: list[str] = []  # "Phat Thai", "Phad Thai"
    # English translation, only when the name is descriptive enough that
    # translating helps ("Pato com batatas" -> "Duck with potatoes"); proper
    # dish names (Francesinha, Phở, Tiramisu) stay null.
    translated_name: str | None = None
    # Name in the dish's original script, when different ("ผัดไทย").
    native_name: str | None = None
    pronunciation: str | None = None  # IPA, e.g. "pʰàt tʰāj"
    summary: str | None = None  # one-liner for list cards
    description: str  # rich text for the detail screen
    origin: str | None = None  # country/region: "Thailand"
    category: str | None = None  # "stir-fried rice-noodle dish"
    national_dish: bool = False  # promoted as a national dish
    allergens: list[Allergen] = []
    dietary: list[DietaryFlag] = []  # diet fit: share of versions worldwide
    ingredients: list[Ingredient] = []  # common ingredients with probability
    macros: Macros | None = None  # whole-dish average per 100 g
    # Vote-aggregated levels — floats, rendered as partially-filled icon bars
    # (e.g. 3.17 chilis out of 5).
    spice_level: float = Field(default=0, ge=0, le=5)
    price_level: float | None = Field(default=None, ge=0, le=5)
    variants: list[DishVariantInfo] = []  # common facets of the family
    similar: list[str] = []  # names of related families ("Pad See Ew")
    # Stored per-language translations; English lives in the base fields.
    translations: list[DishTranslation] = []

    def translation_for(self, language: str) -> DishTranslation | None:
        return next((t for t in self.translations if t.language == language), None)


class DishEnrichment(BaseModel):
    """LLM structured-output target for the per-item enrichment pass.

    The model decides whether the menu item corresponds to a canonical dish
    family at all — a house special or an unrecognizable name yields
    matched=False and the item "stays as written" (no dish link).
    """

    # Whether this menu item maps to a canonical dish family with reasonable
    # confidence. False -> `info` is ignored and the item gets no dish.
    matched: bool
    confidence: float = Field(default=0, ge=0, le=1)
    # The family variant the ITEM matched ("gai" for "Pad Thai Gai"), one of
    # info.variants[].key; null when the item is the generic family dish.
    variant_key: str | None = None
    info: DishInfo | None = None  # required when matched
    # Common ingredients with catalog metadata (localized names) — mirrors
    # info.ingredients but carries the display translations for ingest.
    ingredient_entries: list[IngredientEntry] = []
