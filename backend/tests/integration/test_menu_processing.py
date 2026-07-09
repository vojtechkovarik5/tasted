"""Integration tests for the background scan pipeline (services/processing.py).

MenuProcessor is what the Celery worker runs after upload: extract line items
from each page, resolve each against the dish cache (pgvector), and enrich the
misses into new dishes. It's exercised here end to end against a real database.

Two things shape the setup:

  * The processor opens its OWN session via `app.db.SessionLocal` (the request
    session is long gone by the time the worker runs). That session lives on a
    separate connection and commits progressively, so it can't ride the
    rolled-back `db_session` transaction the other suites use. Instead we point
    `processing.SessionLocal` at the test engine (real commits) and reset the
    schema on teardown. Cross-test isolation still holds: the `engine` fixture
    drop-and-creates at the start of every test.

  * Its two external effects — AI and object storage — are injectable.
    `StubMenuAI` is the deterministic dev adapter (same name → same embedding,
    so cache hits behave exactly as with real embeddings); `_InMemoryStorage`
    stands in for S3/disk. Subclassing the stub lets us force failures.

StubMenuAI.extract_menu always returns two items: "Francesinha" (9.50 EUR) and
"Bacalhau à Brás" (12.00 EUR, allergen hints fish+egg).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models import Base, Dish, Menu, Scan, ScanItem
from app.services.ai import StubMenuAI
from app.services.processing import MenuProcessor


class _InMemoryStorage:
    """Returns fixed bytes for any key — the processor only reads the image."""

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        return key

    async def get(self, key: str) -> bytes:
        return b"\xff\xd8\xff\xe0fake-jpeg-bytes"

    def public_url(self, key: str) -> str:
        return f"/uploads/{key}"


class _RaisingExtractAI(StubMenuAI):
    """Vision call is down — fails the whole page before any items land."""

    async def extract_menu(self, image, media_type):
        raise RuntimeError("vision service unavailable")


class _PartialEnrichAI(StubMenuAI):
    """Enrichment fails for one specific item, succeeds for the rest."""

    async def enrich_dish(self, name, *, hints=None):
        if name == "Francesinha":
            raise RuntimeError("enrichment failed")
        return await super().enrich_dish(name, hints=hints)


@pytest_asyncio.fixture
async def sessionmaker(engine, monkeypatch):
    """A committing session factory bound to the test DB, swapped in for the
    module-level `SessionLocal` the processor opens. Schema is reset afterwards
    so the real writes don't outlive the test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import app.services.processing as processing

    monkeypatch.setattr(processing, "SessionLocal", factory)
    yield factory
    # These tests commit for real (the processor runs on its own connection),
    # so reset the schema afterwards. Dispose first: the committing factory
    # leaves connections idle in the pool, and DROP TABLE would deadlock
    # against the locks they still hold.
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture
def processor() -> MenuProcessor:
    """The processor with deterministic AI and in-memory storage."""
    return MenuProcessor(ai=StubMenuAI(), storage=_InMemoryStorage())


async def _seed_scan(
    factory, *, status: str = "new", items: list[ScanItem] | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Persist a menu with one page; returns (menu_id, scan_id)."""
    async with factory() as s:
        menu = Menu(id=uuid.uuid4())
        scan = Scan(id=uuid.uuid4(), menu_id=menu.id, status=status, image_path="menu.jpg")
        if items is not None:
            scan.items = items
        menu.scans = [scan]
        s.add(menu)
        await s.commit()
        return menu.id, scan.id


async def _read_items(factory, scan_id: uuid.UUID) -> dict[str, dict]:
    async with factory() as s:
        scan = await s.get(Scan, scan_id)
        return {
            i.original_name: {
                "status": i.status,
                "dish_id": i.dish_id,
                "price": i.menu_price,
                "currency": i.menu_price_currency,
            }
            for i in scan.items
        }


async def _read_scan(factory, scan_id: uuid.UUID) -> tuple[str, int]:
    async with factory() as s:
        scan = await s.get(Scan, scan_id)
        return scan.status, scan.attempts


async def _count_dishes(factory) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(Dish))).scalar_one()


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


class TestProcessMenu:
    async def test_resolves_every_item_and_completes_the_page(
        self, sessionmaker, processor
    ):
        menu_id, scan_id = await _seed_scan(sessionmaker)

        should_retry = await processor.process_menu(menu_id)

        assert should_retry is False
        assert await _read_scan(sessionmaker, scan_id) == ("complete", 0)

        items = await _read_items(sessionmaker, scan_id)
        assert set(items) == {"Francesinha", "Bacalhau à Brás"}
        assert all(i["status"] == "ready" for i in items.values())
        assert all(i["dish_id"] is not None for i in items.values())

    async def test_persists_printed_price_and_currency(self, sessionmaker, processor):
        menu_id, scan_id = await _seed_scan(sessionmaker)

        await processor.process_menu(menu_id)

        items = await _read_items(sessionmaker, scan_id)
        assert items["Francesinha"]["price"] == Decimal("9.50")
        assert items["Francesinha"]["currency"] == "EUR"
        assert items["Bacalhau à Brás"]["price"] == Decimal("12.00")

    async def test_misses_are_ingested_as_new_dishes(self, sessionmaker, processor):
        menu_id, _ = await _seed_scan(sessionmaker)

        await processor.process_menu(menu_id)

        # Cache started empty, so both items enriched into fresh dishes.
        assert await _count_dishes(sessionmaker) == 2

    async def test_cache_hit_reuses_dishes_across_menus(self, sessionmaker, processor):
        # First menu populates the cache.
        menu_a, scan_a = await _seed_scan(sessionmaker)
        await processor.process_menu(menu_a)
        assert await _count_dishes(sessionmaker) == 2
        first = {i["dish_id"] for i in (await _read_items(sessionmaker, scan_a)).values()}

        # Second menu with the same items should hit the cache — no new dishes,
        # and its items link to the very same dish rows.
        menu_b, scan_b = await _seed_scan(sessionmaker)
        await processor.process_menu(menu_b)

        assert await _count_dishes(sessionmaker) == 2
        second = {i["dish_id"] for i in (await _read_items(sessionmaker, scan_b)).values()}
        assert second == first

    async def test_resume_skips_extraction_when_items_already_exist(self, sessionmaker):
        # A scan that already holds items (a prior run died mid-enrichment):
        # extraction must be skipped. We prove it by using an AI whose
        # extract_menu raises — if it were called the page would fail.
        items = [
            ScanItem(id=uuid.uuid4(), position=0, original_name="Francesinha", status="pending"),
            ScanItem(id=uuid.uuid4(), position=1, original_name="Bacalhau à Brás", status="pending"),
        ]
        menu_id, scan_id = await _seed_scan(sessionmaker, items=items)
        resumed = MenuProcessor(ai=_RaisingExtractAI(), storage=_InMemoryStorage())

        should_retry = await resumed.process_menu(menu_id)

        assert should_retry is False
        assert (await _read_scan(sessionmaker, scan_id))[0] == "complete"
        resolved = await _read_items(sessionmaker, scan_id)
        assert len(resolved) == 2  # no duplicate line items
        assert all(i["status"] == "ready" for i in resolved.values())


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


class TestFailureHandling:
    async def test_transient_failure_reverts_to_new_for_retry(self, sessionmaker):
        menu_id, scan_id = await _seed_scan(sessionmaker)
        failing = MenuProcessor(ai=_RaisingExtractAI(), storage=_InMemoryStorage())

        should_retry = await failing.process_menu(menu_id)

        assert should_retry is True
        status, attempts = await _read_scan(sessionmaker, scan_id)
        assert status == "new"  # eligible to be reclaimed on reschedule
        assert attempts == 1
        assert await _read_items(sessionmaker, scan_id) == {}

    async def test_gives_up_after_max_attempts(self, sessionmaker, monkeypatch):
        monkeypatch.setattr(settings, "menu_processing_max_attempts", 1)
        menu_id, scan_id = await _seed_scan(sessionmaker)
        failing = MenuProcessor(ai=_RaisingExtractAI(), storage=_InMemoryStorage())

        should_retry = await failing.process_menu(menu_id)

        assert should_retry is False  # out of retries, don't reschedule
        status, attempts = await _read_scan(sessionmaker, scan_id)
        assert status == "complete"  # settled so the client's poll can stop
        assert attempts == 1

    async def test_single_item_enrichment_failure_isolated(self, sessionmaker):
        menu_id, scan_id = await _seed_scan(sessionmaker)
        partial = MenuProcessor(ai=_PartialEnrichAI(), storage=_InMemoryStorage())

        should_retry = await partial.process_menu(menu_id)

        # One bad item doesn't sink the page: it's marked failed, the rest
        # resolve, and the page completes.
        assert should_retry is False
        assert (await _read_scan(sessionmaker, scan_id))[0] == "complete"
        items = await _read_items(sessionmaker, scan_id)
        assert items["Francesinha"]["status"] == "failed"
        assert items["Francesinha"]["dish_id"] is None
        assert items["Bacalhau à Brás"]["status"] == "ready"
        assert await _count_dishes(sessionmaker) == 1  # only the good item ingested

    async def test_no_claimable_scans_is_a_noop(self, sessionmaker, processor):
        # Page already complete — nothing to claim.
        menu_id, scan_id = await _seed_scan(sessionmaker, status="complete")

        should_retry = await processor.process_menu(menu_id)

        assert should_retry is False
        assert (await _read_scan(sessionmaker, scan_id))[0] == "complete"
        assert await _read_items(sessionmaker, scan_id) == {}
        assert await _count_dishes(sessionmaker) == 0
