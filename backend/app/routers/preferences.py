from fastapi import APIRouter

from app.auth import CurrentUserDep
from app.domain import Preferences
from app.services.users import UserServiceDep

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=Preferences)
async def get_preferences(user_id: CurrentUserDep, users: UserServiceDep) -> Preferences:
    """The authenticated user's synced preferences (defaults for anything
    unset). The device keeps the local copy; this is the cross-device sync."""
    return await users.get_preferences(user_id)


@router.put("", response_model=Preferences)
async def put_preferences(
    preferences: Preferences, user_id: CurrentUserDep, users: UserServiceDep
) -> Preferences:
    """Replace the current user's preferences (last-write-wins sync)."""
    return await users.replace_preferences(user_id, preferences)
