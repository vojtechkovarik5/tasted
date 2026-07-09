from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.domain.preferences import Language
from app.services.trackables import localized_name


class TrackableOut(BaseModel):
    """One "What I track" catalog entry, name localized to the requester's
    language (English fallback). `pending` entries are user suggestions not
    yet vetted — only their suggester receives them."""

    id: uuid.UUID
    kind: str  # allergen | dietary | ingredient
    key: str  # canonical slug — what watch_list chips reference
    name: str  # localized display name
    description: str | None = None
    status: str  # active | pending

    @classmethod
    def from_orm_trackable(cls, trackable, language: Language) -> TrackableOut:
        return cls(
            id=trackable.id,
            kind=trackable.kind,
            key=trackable.key,
            name=localized_name(trackable, language),
            description=trackable.description,
            status=trackable.status,
        )


class SuggestTrackableIn(BaseModel):
    """A user-suggested diet flag or ingredient (allergens are fixed).
    Lands as `pending` — an AI check decides later whether it graduates."""

    kind: str  # "dietary" | "ingredient"
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
