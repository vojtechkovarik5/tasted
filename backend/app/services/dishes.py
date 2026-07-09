from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionDep
from app.domain import DishInfo
from app.models import Dish, DishAttribute, DishPhoto, DishVote
from app.repositories import DishRepository, VoteRepository
from app.services.storage import Storage, extension_for, get_storage

# One net vote nudges a 0-100 attribute value by this much (0.2 of an icon).
# Raw votes are kept, so the periodic recalculation task can later replace
# this incremental nudge with a proper aggregate without losing anything.
VOTE_STEP = 4


def _score(probability: float) -> int:
    """0-1 probability -> 0-100 attribute value."""
    return max(0, min(100, round(probability * 100)))


def _level(level: float) -> int:
    """0-5 icon level (spice/price) -> 0-100 attribute value."""
    return max(0, min(100, round(level * 20)))


def attribute_rows(info: DishInfo) -> list[DishAttribute]:
    """Fan a DishInfo's scored fields into dish_attributes rows.

    This is the ingest half of the split: scores live in the table (votable,
    recalculable), only descriptive fields stay in Dish.data. DishOut merges
    them back together on the way out.
    """
    rows = [
        DishAttribute(kind="allergen", key=a.name, value=_score(a.probability))
        for a in info.allergens
    ]
    rows += [
        DishAttribute(kind="dietary", key=d.name, value=_score(d.probability))
        for d in info.dietary
    ]
    rows.append(DishAttribute(kind="spice", value=_level(info.spice_level)))
    if info.price_level is not None:
        rows.append(DishAttribute(kind="price", value=_level(info.price_level)))
    return rows


class DishService:
    """Business logic for dishes; DB access goes through DishRepository."""

    def __init__(self, session: AsyncSession, storage: Storage | None = None):
        self.session = session  # owns the transaction boundary (commit/refresh)
        self.dishes = DishRepository(session)
        self.votes = VoteRepository(session)
        self.storage = storage or get_storage()

    async def get(self, dish_id: uuid.UUID) -> Dish | None:
        return await self.dishes.get(dish_id)

    async def list(self, *, limit: int = 50) -> list[Dish]:
        return await self.dishes.list(limit=limit)

    async def create(
        self,
        info: DishInfo,
        *,
        region: str | None = None,
        embedding: list[float] | None = None,
    ) -> Dish:
        """Ingest a dish into the cache: descriptive fields to Dish.data,
        scored fields fanned into dish_attributes rows."""
        dish = Dish(
            canonical_name=info.original_name,
            region=region or info.origin,
            data=info.model_dump(
                exclude={"allergens", "dietary", "spice_level", "price_level"}
            ),
            name_embedding=embedding,
            attributes=attribute_rows(info),
        )
        self.dishes.add(dish)
        await self.session.commit()
        await self.session.refresh(dish)
        return dish

    async def find_similar(
        self, embedding: list[float], *, max_distance: float = 0.15
    ) -> Dish | None:
        """Semantic dish-cache lookup — the "google each item once, reuse
        forever" core. Nearest cached dish within `max_distance`, else None."""
        return await self.dishes.find_nearest(embedding, max_distance=max_distance)

    async def vote(
        self, dish_id: uuid.UUID, user_id: uuid.UUID, kind: str, direction: int
    ) -> int | None:
        """Record a user's spice/price nudge and shift the displayed value.

        One vote per user per attribute: a repeat in the same direction is a
        no-op, the opposite direction flips the vote. The attribute row is
        read FOR UPDATE and everything commits once at the end, so concurrent
        votes can't lose nudges. Returns the new 0-100 value, or None when
        the dish doesn't exist.
        """
        if await self.dishes.get(dish_id) is None:
            return None
        attr = await self.dishes.get_attribute(dish_id, kind, for_update=True)
        if attr is None:
            # Dish was ingested without this attribute (e.g. unknown price):
            # start from the neutral midpoint.
            attr = DishAttribute(dish_id=dish_id, kind=kind, value=50)
            self.dishes.add(attr)
            await self.dishes.flush()

        existing = await self.votes.get(attr.id, user_id)
        if existing is None:
            self.votes.add(DishVote(attribute_id=attr.id, user_id=user_id, direction=direction))
            delta = direction
        elif existing.direction == direction:
            delta = 0  # idempotent re-vote
        else:
            existing.direction = direction
            delta = 2 * direction  # flip: undo the old vote and apply the new

        attr.value = max(0, min(100, attr.value + VOTE_STEP * delta))
        await self.session.commit()
        return attr.value

    async def add_user_photo(
        self, dish_id: uuid.UUID, data: bytes, content_type: str | None
    ) -> DishPhoto | None:
        """Store a user photo of the dish, pending moderation.

        The photo goes to object storage immediately but only appears in API
        responses once a moderation pass flips its status to `active`
        (DishOut filters on that). Returns None when the dish doesn't exist.
        """
        if await self.dishes.get(dish_id) is None:
            return None
        ext = extension_for(content_type)
        key = f"{settings.app_env}/dishes/{dish_id}/{uuid.uuid4()}{ext}"
        await self.storage.put(key, data, content_type)
        photo = DishPhoto(
            dish_id=dish_id,
            url=self.storage.public_url(key),
            source="user",
            status="pending_moderation",
        )
        self.dishes.add(photo)
        await self.session.commit()
        return photo


def get_dish_service(session: SessionDep) -> DishService:
    return DishService(session)


DishServiceDep = Annotated[DishService, Depends(get_dish_service)]
