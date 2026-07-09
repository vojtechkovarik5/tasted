from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUserDep
from app.domain import LANGUAGE_NAMES, Language, Preferences
from app.services.users import UserServiceDep

router = APIRouter(prefix="/preferences", tags=["preferences"])


class LanguageOut(BaseModel):
    """One row of the language picker."""

    code: str  # ISO 639-1
    name: str  # English display name


class LanguageSelection(BaseModel):
    code: str  # must be one of the supported languages


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


@router.get("/languages", response_model=list[LanguageOut])
async def list_languages() -> list[LanguageOut]:
    """The supported languages — the source for the "My language" picker.

    A fixed allow-list (not DB-driven), English first. Setting a language only
    stores the choice for now; the app stays in English."""
    return [LanguageOut(code=lang.value, name=LANGUAGE_NAMES[lang]) for lang in Language]


@router.post("/language", response_model=LanguageSelection)
async def set_my_language(
    selection: LanguageSelection, user_id: CurrentUserDep, users: UserServiceDep
) -> LanguageSelection:
    """Set the authenticated user's preferred language.

    Validates against the supported set (the picker's source) and persists it
    on the user's prefs."""
    try:
        language = Language(selection.code.lower())
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unsupported language: {selection.code}",
        ) from None
    prefs = await users.update_preferences(user_id, language=language)
    return LanguageSelection(code=prefs.language.value)
