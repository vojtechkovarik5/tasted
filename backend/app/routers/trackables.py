from fastapi import APIRouter, HTTPException, status

from app.auth import CurrentUserDep, OptionalUserDep
from app.domain import Language, Preferences
from app.schemas.trackable import SuggestTrackableIn, TrackableOut
from app.services.trackables import SUGGESTABLE_KINDS, TrackableServiceDep

router = APIRouter(prefix="/trackables", tags=["trackables"])

KINDS = {"allergen", "dietary", "ingredient"}


def _language(user, lang: str | None) -> Language:
    """Explicit ?lang= wins (lets a signed-out device localize), else the
    user's stored preference, else English."""
    if lang:
        try:
            return Language(lang.lower())
        except ValueError:
            pass
    if user is not None:
        return Preferences.model_validate(user.prefs or {}).language
    return Language.en


@router.get("", response_model=list[TrackableOut])
async def list_trackables(
    user: OptionalUserDep,
    trackables: TrackableServiceDep,
    kind: str | None = None,
    q: str | None = None,
    lang: str | None = None,
) -> list[TrackableOut]:
    """The "What I track" catalog: allergens (the fixed EU-14), diet flags
    and ingredients. `q` searches by name (the ingredients "Search any..."
    box). Active entries for everyone, plus the caller's own pending
    suggestions. Names are localized (English fallback)."""
    if kind is not None and kind not in KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown kind: {kind}")
    language = _language(user, lang)
    rows = await trackables.list_catalog(
        kind=kind, query=q, user_id=user.id if user else None
    )
    return [TrackableOut.from_orm_trackable(t, language) for t in rows]


@router.post("/suggest", response_model=TrackableOut)
async def suggest_trackable(
    body: SuggestTrackableIn,
    user_id: CurrentUserDep,
    user: OptionalUserDep,
    trackables: TrackableServiceDep,
) -> TrackableOut:
    """Suggest a new diet flag or ingredient (name + description).

    NOT added to the shared catalog automatically — it lands as `pending`,
    visible only to the suggester (who can track it right away); an AI
    moderation task will decide later whether it makes sense. Allergens and
    macros are fixed and can't be suggested.
    """
    if body.kind not in SUGGESTABLE_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Only dietary flags and ingredients can be suggested",
        )
    try:
        trackable = await trackables.suggest(user_id, body.kind, body.name, body.description)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return TrackableOut.from_orm_trackable(trackable, _language(user, None))
