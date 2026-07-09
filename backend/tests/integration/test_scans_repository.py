"""Integration tests for ScanRepository's claim / cleanup logic.

These cover the state machine that keeps two workers off the same page:
new -> (atomic claim) -> processing -> complete, plus the reset of scans left
stuck in `processing` by a dead worker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select, update

from app.models import Menu, Scan
from app.repositories.scans import ScanRepository


@pytest_asyncio.fixture
async def repo(db_session) -> ScanRepository:
    return ScanRepository(db_session)


async def _make_menu(db_session) -> Menu:
    menu = Menu(id=uuid.uuid4())
    db_session.add(menu)
    await db_session.flush()
    return menu


async def _make_scan(db_session, menu: Menu, status: str = "new") -> Scan:
    scan = Scan(id=uuid.uuid4(), menu_id=menu.id, image_path="k", status=status)
    db_session.add(scan)
    await db_session.flush()
    return scan


async def _age(db_session, scan: Scan, delta: timedelta) -> None:
    """Backdate a scan's updated_at (explicit value bypasses onupdate)."""
    await db_session.execute(
        update(Scan)
        .where(Scan.id == scan.id)
        .values(updated_at=datetime.now(UTC) - delta)
    )


class TestClaimableIds:
    async def test_returns_only_new_scans(self, repo, db_session):
        menu = await _make_menu(db_session)
        new = await _make_scan(db_session, menu, "new")
        await _make_scan(db_session, menu, "processing")
        await _make_scan(db_session, menu, "complete")

        assert await repo.claimable_ids(menu.id) == [new.id]

    async def test_scoped_to_menu(self, repo, db_session):
        menu_a = await _make_menu(db_session)
        menu_b = await _make_menu(db_session)
        await _make_scan(db_session, menu_a, "new")
        b_new = await _make_scan(db_session, menu_b, "new")

        assert await repo.claimable_ids(menu_b.id) == [b_new.id]


class TestClaim:
    async def test_first_claim_wins_second_is_noop(self, repo, db_session):
        menu = await _make_menu(db_session)
        scan = await _make_scan(db_session, menu, "new")

        assert await repo.claim(scan.id) is True
        # No longer `new`, so a second claim (a concurrent run) gets nothing.
        assert await repo.claim(scan.id) is False

        status = await db_session.scalar(select(Scan.status).where(Scan.id == scan.id))
        assert status == "processing"

    async def test_claim_ignores_non_new(self, repo, db_session):
        menu = await _make_menu(db_session)
        scan = await _make_scan(db_session, menu, "complete")

        assert await repo.claim(scan.id) is False


class TestResetStuck:
    async def test_resets_old_processing_and_returns_menu(self, repo, db_session):
        menu = await _make_menu(db_session)
        scan = await _make_scan(db_session, menu, "processing")
        await _age(db_session, scan, timedelta(minutes=30))

        menu_ids = await repo.reset_stuck(timedelta(minutes=10))

        assert menu_ids == [menu.id]
        status = await db_session.scalar(select(Scan.status).where(Scan.id == scan.id))
        assert status == "new"

    async def test_leaves_recent_processing_untouched(self, repo, db_session):
        menu = await _make_menu(db_session)
        scan = await _make_scan(db_session, menu, "processing")  # updated_at = now

        assert await repo.reset_stuck(timedelta(minutes=10)) == []
        status = await db_session.scalar(select(Scan.status).where(Scan.id == scan.id))
        assert status == "processing"

    async def test_leaves_complete_untouched(self, repo, db_session):
        menu = await _make_menu(db_session)
        scan = await _make_scan(db_session, menu, "complete")
        await _age(db_session, scan, timedelta(hours=1))

        assert await repo.reset_stuck(timedelta(minutes=10)) == []
        status = await db_session.scalar(select(Scan.status).where(Scan.id == scan.id))
        assert status == "complete"

    async def test_dedupes_menu_ids(self, repo, db_session):
        menu = await _make_menu(db_session)
        for _ in range(2):
            scan = await _make_scan(db_session, menu, "processing")
            await _age(db_session, scan, timedelta(minutes=30))

        assert await repo.reset_stuck(timedelta(minutes=10)) == [menu.id]
