from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models import UserQuestion
from app.repositories.base import BaseRepository


class QuestionRepository(BaseRepository):
    async def list_for_user(self, user_id: uuid.UUID) -> list[UserQuestion]:
        stmt = (
            select(UserQuestion)
            .where(UserQuestion.user_id == user_id)
            .order_by(UserQuestion.position, UserQuestion.created_at)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def get(self, question_id: uuid.UUID) -> UserQuestion | None:
        return await self.session.get(UserQuestion, question_id)

    async def next_position(self, user_id: uuid.UUID) -> int:
        """The position for an appended question (max + 1, or 0 when empty)."""
        stmt = select(func.max(UserQuestion.position)).where(UserQuestion.user_id == user_id)
        current_max = (await self.session.execute(stmt)).scalar_one_or_none()
        return 0 if current_max is None else current_max + 1

    async def delete(self, question: UserQuestion) -> None:
        await self.session.delete(question)
