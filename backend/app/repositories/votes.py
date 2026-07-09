from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import DishVote
from app.repositories.base import BaseRepository


class VoteRepository(BaseRepository):
    async def get(self, attribute_id: uuid.UUID, user_id: uuid.UUID) -> DishVote | None:
        """This user's existing vote on this attribute, if any."""
        stmt = select(DishVote).where(
            DishVote.attribute_id == attribute_id, DishVote.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
