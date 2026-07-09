"""Background processing of an uploaded menu.

Runs in a Celery worker (see app/tasks.py:process_menu_task) after the upload
request has already returned the menu id, so the client is polling while this
works. Everything is committed progressively — each poll picks up whatever
flipped to `ready` since the last one.

Per scan (= one menu page):

  1. AI extraction: photo -> the printed line items. All items are created as
     `pending` in one commit, so the very next poll shows the full list.
  2. Cache pass: embed every item name (one batch call) and vector-search the
     dishes table. Hits link their dish and flip to `ready` immediately.
  3. Enrichment pass: each miss goes to the AI for full dish info, ingested
     into the cache (dish + attribute rows + embedding) and linked. Items are
     committed one by one; a failed enrichment marks only that item `failed`.

Sequential per menu for now — plenty at this volume, trivially parallelizable
later (per-scan tasks).
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from decimal import Decimal

from app.db import SessionLocal
from app.models import Scan, ScanItem
from app.repositories import ScanRepository
from app.services.ai import MenuAI, get_menu_ai
from app.services.dishes import DishService
from app.services.storage import Storage, get_storage

logger = logging.getLogger(__name__)


class MenuProcessor:
    def __init__(self, ai: MenuAI | None = None, storage: Storage | None = None):
        self.ai = ai or get_menu_ai()
        self.storage = storage or get_storage()

    async def process_menu(self, menu_id: uuid.UUID) -> None:
        """Process every unprocessed page of a menu. Safe to re-run.

        Entry point for the Celery task that wraps us (app/tasks.py). Opens
        its own session — the request's session is long gone.
        """
        async with SessionLocal() as session:
            scans = ScanRepository(session)
            dishes = DishService(session)
            scan_ids = await scans.unprocessed_ids(menu_id)
            if not scan_ids:
                logger.warning("process_menu: nothing to process for menu %s", menu_id)
            for scan_id in scan_ids:
                # Fresh fetch per page — a rollback in a previous iteration
                # leaves earlier-loaded objects expired.
                scan = await scans.get(scan_id)
                try:
                    await self._process_scan(session, scans, dishes, scan)
                except Exception:
                    # Fail the page, not the whole batch: mark what's still
                    # unresolved and let the poll terminate. Statement UPDATEs
                    # (via repo) — session objects are unusable post-rollback.
                    logger.exception("processing scan %s failed", scan_id)
                    await session.rollback()
                    await scans.fail_pending_items(scan_id)
                    await scans.set_scan_status(scan_id, "complete")
                    await session.commit()

    async def _process_scan(
        self, session, scans: ScanRepository, dishes: DishService, scan: Scan
    ) -> None:
        image = await self.storage.get(scan.image_path)
        media_type, _ = mimetypes.guess_type(scan.image_path)

        # 1. extraction — one commit, so the next poll shows every item.
        extraction = await self.ai.extract_menu(image, media_type)
        items = [
            ScanItem(
                scan_id=scan.id,
                position=i,
                original_name=extracted.name,
                menu_price=Decimal(str(extracted.price)) if extracted.price is not None else None,
                menu_price_currency=extracted.currency,
            )
            for i, extracted in enumerate(extraction.items)
        ]
        scans.add_items(items)
        await session.commit()

        # 2. cache pass — hits flip to ready in one commit.
        embeddings = await self.ai.embed([item.original_name for item in items])
        misses: list[tuple[ScanItem, list[float]]] = []
        for item, embedding in zip(items, embeddings, strict=True):
            dish = await dishes.find_similar(embedding)
            if dish is not None:
                item.dish_id = dish.id
                item.status = "ready"
            else:
                misses.append((item, embedding))
        await session.commit()

        # 3. enrichment pass — misses become dishes, committed per item so each
        # poll picks up whatever finished since the last one.
        hints_by_name = {e.name: e.allergen_hints for e in extraction.items}
        for item, embedding in misses:
            try:
                info = await self.ai.enrich_dish(
                    item.original_name, hints=hints_by_name.get(item.original_name)
                )
                dish = await dishes.create(info, embedding=embedding)
                item.dish_id = dish.id
                item.status = "ready"
            except Exception:
                logger.exception("enriching %r failed", item.original_name)
                item.status = "failed"
            await session.commit()

        scan.status = "complete"
        await session.commit()
