from __future__ import annotations

from pydantic import BaseModel, Field


class Allergen(BaseModel):
    name: str  # "gluten", "egg", "milk", "pork", "fish", ...
    probability: float = Field(ge=0, le=1)  # rendered as "gluten 99%"


class DietaryFlag(BaseModel):
    """Probability that the dish satisfies a diet (NOT that it violates it).

    "vegetarian 0.02" -> almost certainly not vegetarian; the UI renders it
    as a conflict ("x 2%") when the user tracks that diet.
    """

    name: str  # "vegetarian", "vegan", "halal", ...
    probability: float = Field(ge=0, le=1)


class Macros(BaseModel):
    """Estimated macros per typical serving — shown on list cards when the
    user tracks them (Preferences.macros)."""

    kcal: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)


class DishInfo(BaseModel):
    """Canonical knowledge about a single dish — the core domain model.

    Doubles as the LLM's structured-output target and as the JSON payload
    stored in `Dish.data` — except the scored fields (allergens, dietary,
    spice_level, price_level), which are persisted as `dish_attributes` rows
    so they can be voted on, and merged back in by `DishOut.from_orm_dish`.
    """

    original_name: str
    aliases: list[str] = []  # "Francesinha à moda do Porto", "little Frenchie"
    # English translation, only when the name is descriptive enough that
    # translating helps ("Pato com batatas" -> "Duck with potatoes"); proper
    # dish names (Francesinha, Phở, Tiramisu) stay null.
    translated_name: str | None = None
    summary: str | None = None  # one-liner for list cards
    description: str  # rich text for the detail screen
    origin: str | None = None
    allergens: list[Allergen] = []
    dietary: list[DietaryFlag] = []
    macros: Macros | None = None  # estimated per typical serving
    # Vote-aggregated levels — floats, rendered as partially-filled icon bars
    # (e.g. 3.17 chilis out of 5).
    spice_level: float = Field(default=0, ge=0, le=5)
    price_level: float | None = Field(default=None, ge=0, le=5)
