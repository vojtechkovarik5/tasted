from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.models import Scan, ScanItem
from app.repositories.base import BaseRepository


class ScanRepository(BaseRepository):
    """Scan + scan-item persistence, used by the worker-side processor."""

    async def claimable_ids(self, menu_id: uuid.UUID) -> list[uuid.UUID]:
        """Scans waiting to be picked up (status == new). A scan already in
        `processing` belongs to another worker, so it's not a candidate."""
        stmt = select(Scan.id).where(Scan.menu_id == menu_id, Scan.status == "new")
        return list((await self.session.execute(stmt)).scalars())

    async def claim(self, scan_id: uuid.UUID) -> bool:
        """Atomically move a scan new -> processing.

        Returns True only for the caller that won the row (rowcount == 1); a
        concurrent worker's UPDATE blocks on the row lock, then matches nothing
        once this commits and gets False. That's what stops two workers from
        processing the same scan. Caller must commit to release the claim.
        """
        result = await self.session.execute(
            update(Scan)
            .where(Scan.id == scan_id, Scan.status == "new")
            .values(status="processing", updated_at=func.now())
        )
        return result.rowcount == 1

    async def reset_stuck(self, older_than: timedelta) -> list[uuid.UUID]:
        """Reclaim scans stuck in `processing` (worker died mid-page): flip them
        back to `new` so they get reprocessed, and return the distinct menu ids
        to reschedule. `updated_at` is when the claim happened.
        """
        cutoff = datetime.now(UTC) - older_than
        stmt = (
            update(Scan)
            .where(Scan.status == "processing", Scan.updated_at < cutoff)
            .values(status="new", updated_at=func.now())
            .returning(Scan.menu_id)
        )
        menu_ids = (await self.session.execute(stmt)).scalars().all()
        return list(dict.fromkeys(menu_ids))  # distinct, order-preserving

    async def get(self, scan_id: uuid.UUID) -> Scan | None:
        return await self.session.get(Scan, scan_id)

    def add_items(self, items: list[ScanItem]) -> None:
        self.session.add_all(items)

    async def set_scan_status(self, scan_id: uuid.UUID, status: str) -> None:
        """Status update by id (safe after a rollback — no stale ORM state)."""
        await self.session.execute(
            update(Scan).where(Scan.id == scan_id).values(status=status, updated_at=func.now())
        )

    async def register_failure(self, scan_id: uuid.UUID) -> int:
        """Increment the scan's attempt counter; returns the new total. Used by
        the processor to decide between retry and give-up (statement UPDATE, so
        it's safe after a rollback)."""
        stmt = (
            update(Scan)
            .where(Scan.id == scan_id)
            .values(attempts=Scan.attempts + 1, updated_at=func.now())
            .returning(Scan.attempts)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def fail_pending_items(self, scan_id: uuid.UUID) -> None:
        await self.session.execute(
            update(ScanItem)
            .where(ScanItem.scan_id == scan_id, ScanItem.status == "pending")
            .values(status="failed")
        )
