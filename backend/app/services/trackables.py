from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionDep
from app.domain import IngredientEntry, Language
from app.domain.catalog import slugify
from app.models import Trackable
from app.repositories.trackables import TrackableRepository

# Allergens are the fixed EU-14 — never suggestable. Macros aren't catalog
# entries at all (a fixed enum in preferences), so they don't appear here.
SUGGESTABLE_KINDS = {"dietary", "ingredient"}


def localized_name(trackable: Trackable, language: Language) -> str:
    """The catalog entry's display name in the user's language, falling back
    to English (the `name` column)."""
    entry = (trackable.translations or {}).get(language.value) or {}
    return entry.get("name") or trackable.name


class TrackableService:
    """The "What I track" catalog: list/search, user suggestions (pending),
    and the label resolver every read path uses to localize canonical slugs."""

    def __init__(self, session: AsyncSession):
        self.session = session  # owns the transaction boundary
        self.trackables = TrackableRepository(session)

    async def list_catalog(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[Trackable]:
        return await self.trackables.list(
            kind=kind, query=query, include_pending_of=user_id
        )

    async def suggest(
        self, user_id: uuid.UUID, kind: str, name: str, description: str | None
    ) -> Trackable:
        """A user-suggested diet flag or ingredient. Stored as `pending` —
        NOT auto-approved; an AI moderation task will decide later whether it
        graduates to active (not implemented yet). The suggester can track it
        immediately. Suggesting something that already exists returns the
        existing entry instead of erroring — the intent ("track this") is met.
        """
        if kind not in SUGGESTABLE_KINDS:
            raise ValueError(f"Cannot suggest a {kind}")
        key = slugify(name)
        if not key:
            raise ValueError("Name is required")
        existing = await self.trackables.get_by_key(kind, key)
        if existing is not None:
            return existing
        trackable = Trackable(
            kind=kind,
            key=key,
            name=name.strip(),
            description=(description or "").strip() or None,
            status="pending",
            suggested_by=user_id,
        )
        self.trackables.add(trackable)
        await self.session.commit()
        return trackable

    async def ensure_ingredients(self, entries: list[IngredientEntry]) -> None:
        """Ingest pass: make sure every ingredient the enrichment mentioned
        exists in the catalog (active) with its localized names, so tags and
        settings search can resolve the slug everywhere. Commits."""
        for entry in entries:
            key = slugify(entry.key or entry.name)
            if not key:
                continue
            translations = {t.language: t.name for t in entry.translations if t.name}
            await self.trackables.upsert_ingredient(
                key, entry.name.strip() or key, translations
            )
        await self.session.commit()

    async def labels(
        self, pairs: set[tuple[str, str]], language: Language
    ) -> dict[tuple[str, str], str]:
        """(kind, key) -> localized display name, English fallback; keys not
        in the catalog fall back to a humanized slug ("rice-noodles" ->
        "rice noodles") so nothing renders as a raw slug."""
        rows = await self.trackables.by_keys(pairs)
        found = {(t.kind, t.key): localized_name(t, language) for t in rows}
        return {
            pair: found.get(pair, pair[1].replace("-", " ")) for pair in pairs
        }


def get_trackable_service(session: SessionDep) -> TrackableService:
    return TrackableService(session)


TrackableServiceDep = Annotated[TrackableService, Depends(get_trackable_service)]
