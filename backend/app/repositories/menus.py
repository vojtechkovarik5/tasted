from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Menu
from app.repositories.base import BaseRepository


class MenuRepository(BaseRepository):
    async def get(self, menu_id: uuid.UUID) -> Menu | None:
        """Menu with scans + items eager-loaded (selectin on the relations)."""
        return await self.session.get(Menu, menu_id)

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Menu]:
        stmt = (
            select(Menu)
            .where(Menu.user_id == user_id)
            .order_by(Menu.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, menu: Menu) -> None:
        """Stage the menu for deletion; scans + items go with it (FK CASCADE)."""
        await self.session.delete(menu)
