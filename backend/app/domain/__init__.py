"""Domain models — plain pydantic value objects the services speak in.

These are neither ORM (persistence, app/models) nor API wire shapes
(app/schemas). Repositories return ORM; services synthesize these when they
need to hand back a plain object; API schemas wrap/reference them at the edge.
"""

from app.domain.dish import Allergen, DietaryFlag, DishInfo, Macros
from app.domain.menu import ExtractedGroup, ExtractedMenuItem, MenuExtraction, Money
from app.domain.preferences import LANGUAGE_NAMES, Language, Preferences, WatchChip
from app.domain.question import SuggestedQuestions, TranslatedQuestions

__all__ = [
    "Allergen",
    "DietaryFlag",
    "DishInfo",
    "ExtractedGroup",
    "ExtractedMenuItem",
    "LANGUAGE_NAMES",
    "Language",
    "Macros",
    "MenuExtraction",
    "Money",
    "Preferences",
    "SuggestedQuestions",
    "TranslatedQuestions",
    "WatchChip",
]
