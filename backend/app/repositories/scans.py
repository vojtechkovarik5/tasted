from __future__ import annotations

import uuid

from sqlalchemy import select, update

from app.models import Scan, ScanItem
from app.repositories.base import BaseRepository


class ScanRepository(BaseRepository):
    """Scan + scan-item persistence, used by the worker-side processor."""

    async def unprocessed_ids(self, menu_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Scan.id).where(Scan.menu_id == menu_id, Scan.status != "complete")
        return list((await self.session.execute(stmt)).scalars())

    async def get(self, scan_id: uuid.UUID) -> Scan | None:
        return await self.session.get(Scan, scan_id)

    def add_items(self, items: list[ScanItem]) -> None:
        self.session.add_all(items)

    async def set_scan_status(self, scan_id: uuid.UUID, status: str) -> None:
        """Status update by id (safe after a rollback — no stale ORM state)."""
        await self.session.execute(
            update(Scan).where(Scan.id == scan_id).values(status=status)
        )

    async def fail_pending_items(self, scan_id: uuid.UUID) -> None:
        await self.session.execute(
            update(ScanItem)
            .where(ScanItem.scan_id == scan_id, ScanItem.status == "pending")
            .values(status="failed")
        )
