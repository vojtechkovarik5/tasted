from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.models import Trackable
from app.repositories.base import BaseRepository


class TrackableRepository(BaseRepository):
    async def get_by_key(self, kind: str, key: str) -> Trackable | None:
        stmt = select(Trackable).where(Trackable.kind == kind, Trackable.key == key)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        include_pending_of: uuid.UUID | None = None,
        limit: int = 500,
    ) -> list[Trackable]:
        """Catalog listing: active entries, plus the caller's own pending
        suggestions (they can track them right away; nobody else sees them
        until moderation graduates the entry)."""
        stmt = select(Trackable)
        if kind is not None:
            stmt = stmt.where(Trackable.kind == kind)
        if include_pending_of is not None:
            stmt = stmt.where(
                or_(
                    Trackable.status == "active",
                    Trackable.suggested_by == include_pending_of,
                )
            )
        else:
            stmt = stmt.where(Trackable.status == "active")
        if query:
            stmt = stmt.where(Trackable.name.ilike(f"%{query.strip()}%"))
        stmt = stmt.order_by(Trackable.name).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def by_keys(self, pairs: set[tuple[str, str]]) -> list[Trackable]:
        """All catalog rows for a set of (kind, key) pairs — the label
        resolver's one query."""
        if not pairs:
            return []
        conditions = [
            (Trackable.kind == kind) & (Trackable.key == key) for kind, key in pairs
        ]
        stmt = select(Trackable).where(or_(*conditions))
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_ingredient(
        self, key: str, name: str, translations: dict[str, str]
    ) -> None:
        """Insert an AI-encountered ingredient as active; on conflict merge
        translations the existing row doesn't have yet (first writer wins per
        language, so vetted names aren't churned by later scans)."""
        stored = {lang: {"name": text} for lang, text in translations.items() if text}
        stmt = insert(Trackable).values(
            id=uuid.uuid4(),
            kind="ingredient",
            key=key,
            name=name,
            translations=stored,
            status="active",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Trackable.kind, Trackable.key],
            set_={"translations": stmt.excluded.translations.concat(Trackable.translations)},
        )
        await self.session.execute(stmt)
