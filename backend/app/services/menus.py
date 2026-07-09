from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionDep
from app.models import Menu, Scan, ScanItem
from app.repositories import MenuRepository
from app.services.storage import Storage, extension_for, get_storage


@dataclass
class PhotoUpload:
    """One uploaded menu page, decoupled from FastAPI's UploadFile so the
    service can be driven from tests/scripts too."""

    data: bytes
    content_type: str | None = None


class MenuService:
    """Create/read menus — the scan batches. Processing lives in
    services/processing.py; this service never calls the AI."""

    def __init__(self, session: AsyncSession, storage: Storage | None = None):
        self.session = session  # owns the transaction boundary
        self.menus = MenuRepository(session)
        self.storage = storage or get_storage()

    async def create_with_photos(
        self,
        photos: list[PhotoUpload],
        *,
        user_id: uuid.UUID | None = None,
        name: str | None = None,
    ) -> Menu:
        """Store the uploaded pages and return the menu immediately.

        Fast path behind the upload request: push each page to object storage,
        create menu + one `Scan` per page in the `new` state (storage key kept
        in `image_path`), and return — mainly so the client has the menu id to
        poll. No AI here; the caller enqueues the pipeline afterwards via
        process_menu_task.delay(menu.id), and the worker claims each new scan
        (new -> processing -> complete).
        """
        menu = Menu(id=uuid.uuid4(), user_id=user_id, name=name)

        # TODO gather
        for photo in photos:
            scan_id = uuid.uuid4()
            ext = extension_for(photo.content_type)
            # env-prefixed so environments don't collide in a shared bucket.
            key = f"{settings.app_env}/menus/{menu.id}/{scan_id}{ext}"
            stored_key = await self.storage.put(key, photo.data, photo.content_type)
            menu.scans.append(
                Scan(
                    id=scan_id,
                    image_path=stored_key,
                    image_sha256=hashlib.sha256(photo.data).hexdigest(),
                )
            )

        self.menus.add(menu)
        await self.session.commit()
        await self.session.refresh(menu)
        return menu

    async def get(self, menu_id: uuid.UUID) -> Menu | None:
        """Menu with scans + items (selectin) — what the client polls."""
        return await self.menus.get(menu_id)

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Menu]:
        """Scan history in the profile: the user's menus, newest first."""
        return await self.menus.list_for_user(user_id, limit=limit)

    @staticmethod
    def combined_items(menu: Menu) -> list[ScanItem]:
        """The menu's items across all pages, in page/print order.

        Items that resolved to the same dish (it appears on two pages, or the
        same page was uploaded twice) are collapsed to their first occurrence;
        unresolved items are always kept.
        """
        seen: set[uuid.UUID] = set()
        items: list[ScanItem] = []
        for scan in menu.scans:
            for item in scan.items:
                if item.dish_id is not None:
                    if item.dish_id in seen:
                        continue
                    seen.add(item.dish_id)
                items.append(item)
        return items


def get_menu_service(session: SessionDep) -> MenuService:
    return MenuService(session)


MenuServiceDep = Annotated[MenuService, Depends(get_menu_service)]
