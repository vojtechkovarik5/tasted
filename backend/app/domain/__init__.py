"""Domain models — plain pydantic value objects the services speak in.

These are neither ORM (persistence, app/models) nor API wire shapes
(app/schemas). Repositories return ORM; services synthesize these when they
need to hand back a plain object; API schemas wrap/reference them at the edge.
"""

from app.domain.dish import (
    Allergen,
    DietaryFlag,
    DishEnrichment,
    DishInfo,
    DishTranslation,
    DishVariantInfo,
    Ingredient,
    IngredientEntry,
    Macros,
    NameTranslation,
)
from app.domain.menu import (
    ExtractedGroup,
    ExtractedIngredient,
    ExtractedMenuItem,
    MenuExtraction,
    Money,
)
from app.domain.preferences import LANGUAGE_NAMES, Language, Preferences, WatchChip
from app.domain.question import SuggestedQuestions, TranslatedQuestions

__all__ = [
    "Allergen",
    "DietaryFlag",
    "DishEnrichment",
    "DishInfo",
    "DishTranslation",
    "DishVariantInfo",
    "ExtractedGroup",
    "ExtractedIngredient",
    "ExtractedMenuItem",
    "Ingredient",
    "IngredientEntry",
    "LANGUAGE_NAMES",
    "Language",
    "Macros",
    "MenuExtraction",
    "Money",
    "NameTranslation",
    "Preferences",
    "SuggestedQuestions",
    "TranslatedQuestions",
    "WatchChip",
]
