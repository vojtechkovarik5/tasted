"""Repository layer — wraps all DB access, returns ORM objects.

Services depend on these instead of touching the session directly; the
transaction boundary is controlled via BaseRepository.commit/flush.
"""

from app.repositories.base import BaseRepository
from app.repositories.currencies import CurrencyRepository
from app.repositories.dishes import DishRepository
from app.repositories.menus import MenuRepository
from app.repositories.questions import QuestionRepository
from app.repositories.scans import ScanRepository
from app.repositories.trackables import TrackableRepository
from app.repositories.users import UserRepository
from app.repositories.votes import VoteRepository

__all__ = [
    "BaseRepository",
    "CurrencyRepository",
    "DishRepository",
    "MenuRepository",
    "QuestionRepository",
    "ScanRepository",
    "TrackableRepository",
    "UserRepository",
    "VoteRepository",
]
