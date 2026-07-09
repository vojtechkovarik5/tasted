from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionDep
from app.domain import Preferences, WatchChip
from app.models import User
from app.repositories import UserRepository


class UserService:
    """Users and their synced preferences.

    Identity is owned by Clerk; rows are created lazily on first
    authenticated request. DB access goes through UserRepository; the prefs
    methods return the `Preferences` domain model (not the ORM row).
    """

    def __init__(self, session: AsyncSession):
        self.session = session  # owns the transaction boundary
        self.users = UserRepository(session)

    async def get_or_create_by_clerk_id(
        self, clerk_user_id: str, *, email: str | None = None, display_name: str | None = None
    ) -> User:
        """Return the user for this Clerk `sub`, creating the row if needed.

        Insert-ignore then read, so concurrent first-requests don't race into
        an IntegrityError.
        """
        await self.users.insert_ignoring_conflict(
            clerk_user_id, email=email, display_name=display_name
        )
        await self.session.commit()
        return await self.users.get_by_clerk_id(clerk_user_id)

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.users.get(user_id)

    async def get_preferences(self, user_id: uuid.UUID) -> Preferences:
        """The user's prefs, filled with defaults for anything unset."""
        user = await self.users.get(user_id)
        return Preferences.model_validate(user.prefs or {}) if user else Preferences()

    async def replace_preferences(self, user_id: uuid.UUID, prefs: Preferences) -> Preferences:
        user = await self.users.get(user_id)
        user.prefs = prefs.model_dump(mode="json")
        await self.session.commit()
        return prefs

    async def update_preferences(self, user_id: uuid.UUID, **fields) -> Preferences:
        """Patch specific preference fields (e.g. currency) in place."""
        user = await self.users.get(user_id)
        updated = Preferences.model_validate(user.prefs or {}).model_copy(update=fields)
        user.prefs = updated.model_dump(mode="json")
        await self.session.commit()
        return updated

    async def get_watch_keys(self, user_id: uuid.UUID, kind: str) -> list[str]:
        """Active "Watch out for" chips of one kind ("allergen" | "dietary")."""
        prefs = await self.get_preferences(user_id)
        return [c.key for c in prefs.watch_list if c.kind == kind and c.on]

    async def set_watch_keys(self, user_id: uuid.UUID, kind: str, keys: list[str]) -> list[str]:
        """Replace the watch chips of one kind, leaving the other kind alone.

        The chips UI always posts the full set for its kind, so this is a
        replace, not a merge. Order is preserved as sent.
        """
        prefs = await self.get_preferences(user_id)
        others = [c for c in prefs.watch_list if c.kind != kind]
        chips = [WatchChip(key=k, kind=kind) for k in keys]
        await self.update_preferences(user_id, watch_list=others + chips)
        return keys


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
