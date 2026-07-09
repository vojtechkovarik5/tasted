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

from app.config import settings
from app.db import SessionLocal
from app.domain import ExtractedMenuItem, Language, Preferences
from app.models import Menu, Scan, ScanItem, User
from app.repositories import ScanRepository
from app.services.ai import MenuAI, get_menu_ai
from app.services.dishes import DishService
from app.services.storage import Storage, get_storage

logger = logging.getLogger(__name__)


class MenuProcessor:
    def __init__(self, ai: MenuAI | None = None, storage: Storage | None = None):
        self.ai = ai or get_menu_ai()
        self.storage = storage or get_storage()

    async def process_menu(self, menu_id: uuid.UUID) -> bool:
        """Process every unprocessed page of a menu. Safe to re-run.

        Entry point for the Celery task that wraps us (app/tasks.py). Opens
        its own session — the request's session is long gone.

        Returns True if a page failed transiently and was reverted to `new` for
        retry, so the caller should reschedule the menu.
        """
        should_retry = False
        async with SessionLocal() as session:
            scans = ScanRepository(session)
            dishes = DishService(session)
            scan_ids = await scans.claimable_ids(menu_id)
            if not scan_ids:
                logger.warning("process_menu: nothing to process for menu %s", menu_id)
            # Extraction translates into the scanning user's language; the
            # anonymous default is English (Preferences().language).
            user_language = await self._user_language(session, menu_id)
            for scan_id in scan_ids:
                # Atomically claim the page (new -> processing) so a concurrent
                # run of this task — a duplicate delivery, or a reschedule that
                # overlaps a still-running worker — can't process it too.
                if not await scans.claim(scan_id):
                    logger.info("process_menu: scan %s already claimed, skipping", scan_id)
                    continue
                await session.commit()  # release the claim so others see it
                # Fresh fetch per page — a rollback in a previous iteration
                # leaves earlier-loaded objects expired.
                scan = await scans.get(scan_id)
                try:
                    await self._process_scan(session, scans, dishes, scan, user_language)
                except Exception:
                    # Don't sink the whole batch on one page. Statement UPDATEs
                    # (via repo) — session objects are unusable post-rollback.
                    logger.exception("processing scan %s failed", scan_id)
                    await session.rollback()
                    attempts = await scans.register_failure(scan_id)
                    if attempts < settings.menu_processing_max_attempts:
                        # Transient (e.g. AI hiccup) — revert to `new` so a
                        # reschedule retries it; extraction is skipped if items
                        # already landed, so the retry resumes, not restarts.
                        await scans.set_scan_status(scan_id, "new")
                        should_retry = True
                    else:
                        # Out of retries: mark unresolved items failed and let
                        # the page settle so the poll can terminate.
                        logger.error("giving up on scan %s after %d attempts", scan_id, attempts)
                        await scans.fail_pending_items(scan_id)
                        await scans.set_scan_status(scan_id, "complete")
                    await session.commit()
        return should_retry

    async def _user_language(self, session, menu_id: uuid.UUID) -> Language:
        """The menu owner's preferred language (extraction translates into
        it). Anonymous menus fall back to the Preferences default."""
        menu = await session.get(Menu, menu_id)
        if menu is not None and menu.user_id is not None:
            user = await session.get(User, menu.user_id)
            if user is not None:
                return Preferences.model_validate(user.prefs or {}).language
        return Preferences().language

    async def _process_scan(
        self,
        session,
        scans: ScanRepository,
        dishes: DishService,
        scan: Scan,
        user_language: Language,
    ) -> None:
        # 1. extraction — one commit, so the next poll shows every item.
        # Resumable: a rescheduled scan that already holds items (a prior run
        # died mid-enrichment) skips extraction entirely, so we never re-fetch
        # the image, re-run the vision call, or duplicate line items.
        extracted_by_name: dict[str, ExtractedMenuItem] = {}
        if scan.items:
            items = list(scan.items)
        else:
            image = await self.storage.get(scan.image_path)
            media_type, _ = mimetypes.guess_type(scan.image_path)
            extraction = await self.ai.extract_menu(
                image, media_type, user_language=user_language
            )
            # The vision pass reads the menu's printed language for free —
            # keep it on the menu (first page wins) for ask-staff translations.
            if extraction.language:
                menu = await session.get(Menu, scan.menu_id)
                if menu.language is None:
                    menu.language = extraction.language
            group_translations = {g.name: g.translated_name for g in extraction.groups}
            items = [
                ScanItem(
                    scan_id=scan.id,
                    position=i,
                    original_name=extracted.name,
                    menu_number=extracted.number,
                    translated_name=extracted.translated_name,
                    menu_description=extracted.description,
                    menu_description_translated=extracted.translated_description,
                    group_name=extracted.group,
                    group_name_translated=(
                        group_translations.get(extracted.group) if extracted.group else None
                    ),
                    menu_price=(
                        Decimal(str(extracted.price)) if extracted.price is not None else None
                    ),
                    menu_price_currency=extracted.currency,
                )
                for i, extracted in enumerate(extraction.items)
            ]
            extracted_by_name = {e.name: e for e in extraction.items}
            scans.add_items(items)
            await session.commit()

        # Only items not already resolved — on a resume the already-ready ones
        # (linked to a dish in a prior run) are skipped; pending/failed retry.
        todo = [item for item in items if item.status != "ready"]

        # 2. cache pass — hits flip to ready in one commit.
        embeddings = await self.ai.embed([item.original_name for item in todo])
        misses: list[tuple[ScanItem, list[float]]] = []
        for item, embedding in zip(todo, embeddings, strict=True):
            dish = await dishes.find_similar(embedding)
            if dish is not None:
                item.dish_id = dish.id
                item.status = "ready"
            else:
                misses.append((item, embedding))
        await session.commit()

        # 3. enrichment pass — misses become dishes, committed per item so each
        # poll picks up whatever finished since the last one.
        for item, embedding in misses:
            extracted = extracted_by_name.get(item.original_name)
            try:
                info = await self.ai.enrich_dish(
                    item.original_name,
                    hints=extracted.allergen_hints if extracted else None,
                    # Extra context only — canonical dish info stays generic.
                    menu_description=item.menu_description,
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
