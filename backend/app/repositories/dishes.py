from __future__ import annotations

import uuid

from sqlalchemy import select, text

from app.models import Dish, DishAttribute
from app.repositories.base import BaseRepository


class DishRepository(BaseRepository):
    async def get(self, dish_id: uuid.UUID) -> Dish | None:
        return await self.session.get(Dish, dish_id)

    async def get_attribute(
        self, dish_id: uuid.UUID, kind: str, key: str | None = None, *, for_update: bool = False
    ) -> DishAttribute | None:
        """One attribute row of a dish (kind + optional key).

        `for_update` row-locks it for a read-modify-write (vote nudges) —
        the caller must hold off committing until its update is staged.
        """
        stmt = select(DishAttribute).where(
            DishAttribute.dish_id == dish_id,
            DishAttribute.kind == kind,
            DishAttribute.key == key,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def recalculate_values(self, vote_step: int) -> int:
        """Recompute every voted attribute's displayed value from its AI
        baseline and the net vote count, in one statement:

            value = clamp(base_value + vote_step * SUM(direction), 0, 100)

        Attributes without votes keep their baseline untouched; rows already
        at the right value are skipped so updated_at only moves on change.
        Returns the number of rows updated.
        """
        stmt = text(
            """
            UPDATE dish_attributes a
            SET value = LEAST(100, GREATEST(0, a.base_value + :step * v.net)),
                updated_at = now()
            FROM (
                SELECT attribute_id, SUM(direction)::int AS net
                FROM dish_votes
                GROUP BY attribute_id
            ) v
            WHERE v.attribute_id = a.id
              AND a.value IS DISTINCT FROM
                  LEAST(100, GREATEST(0, a.base_value + :step * v.net))
            """
        )
        result = await self.session.execute(stmt, {"step": vote_step})
        return result.rowcount or 0

    async def list(self, *, limit: int = 50) -> list[Dish]:
        stmt = select(Dish).order_by(Dish.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_nearest(
        self, embedding: list[float], *, max_distance: float
    ) -> Dish | None:
        """Nearest dish by cosine distance within `max_distance`, else None."""
        distance = Dish.name_embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(Dish, distance)
            .where(Dish.name_embedding.isnot(None))
            .order_by(distance)
            .limit(1)
        )
        row = (await self.session.execute(stmt)).first()
        if row is not None and row.distance <= max_distance:
            return row[0]
        return None
