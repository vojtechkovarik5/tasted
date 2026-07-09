from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def insert_ignoring_conflict(
        self, clerk_user_id: str, *, email: str | None, display_name: str | None
    ) -> None:
        """Insert a user, doing nothing if the clerk id already exists.

        Race-safe first-login create; the caller commits, then reads the row
        back with get_by_clerk_id (whether we or a concurrent request wrote it).
        """
        stmt = (
            insert(User)
            .values(clerk_user_id=clerk_user_id, email=email, display_name=display_name)
            .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
        )
        await self.session.execute(stmt)
