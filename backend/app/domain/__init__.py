"""Domain models — plain pydantic value objects the services speak in.

These are neither ORM (persistence, app/models) nor API wire shapes
(app/schemas). Repositories return ORM; services synthesize these when they
need to hand back a plain object; API schemas wrap/reference them at the edge.
"""

from app.domain.dish import Allergen, DietaryFlag, DishInfo
from app.domain.menu import ExtractedMenuItem, MenuExtraction, Money
from app.domain.preferences import LANGUAGE_NAMES, Language, Preferences, WatchChip
from app.domain.question import SuggestedQuestions

__all__ = [
    "Allergen",
    "DietaryFlag",
    "DishInfo",
    "ExtractedMenuItem",
    "LANGUAGE_NAMES",
    "Language",
    "MenuExtraction",
    "Money",
    "Preferences",
    "SuggestedQuestions",
    "WatchChip",
]
