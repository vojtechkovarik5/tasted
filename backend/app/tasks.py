"""Celery tasks. Thin sync wrappers — the real logic stays in services."""

import asyncio
import logging
import uuid
from decimal import Decimal

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"


@celery_app.task(name="process_menu")
def process_menu_task(menu_id: str) -> None:
    """Run the scan pipeline for one menu (see services/processing.py)."""
    # Imported here so the celery CLI can load app.tasks without pulling the
    # whole app graph at module import.
    from app.config import settings
    from app.db import engine
    from app.services.processing import MenuProcessor

    async def run() -> bool:
        try:
            return await MenuProcessor().process_menu(uuid.UUID(menu_id))
        finally:
            # Each task runs in its own event loop (asyncio.run) but the
            # engine's pool outlives it, and asyncpg connections are bound to
            # the loop that created them. Dispose so the next task on this
            # worker process starts with a fresh pool on its own loop.
            await engine.dispose()

    if asyncio.run(run()):
        # A page failed transiently and was reverted to `new`; retry the menu
        # after a short delay so the reverted page gets picked up again.
        process_menu_task.apply_async(
            (menu_id,), countdown=settings.menu_processing_retry_delay_seconds
        )


@celery_app.task(name="reschedule_stuck_menus")
def reschedule_stuck_menus_task() -> None:
    """Recover menus stuck mid-processing.

    A page claimed by a worker that then died stays `processing` forever — no
    other run will touch it (only `new` scans are claimable). This beat task
    (see celery_app) resets scans that have sat in `processing` past
    settings.menu_processing_stale_after_seconds back to `new` and re-enqueues
    their menus, so the reset pages get picked up and reprocessed.
    """
    from datetime import timedelta

    from app.config import settings
    from app.db import SessionLocal, engine
    from app.repositories.scans import ScanRepository

    async def run() -> None:
        try:
            stale_after = timedelta(seconds=settings.menu_processing_stale_after_seconds)
            async with SessionLocal() as session:
                menu_ids = await ScanRepository(session).reset_stuck(stale_after)
                await session.commit()
            for menu_id in menu_ids:
                process_menu_task.delay(str(menu_id))
            if menu_ids:
                logger.warning("rescheduled %d stuck menu(s): %s", len(menu_ids), menu_ids)
        finally:
            await engine.dispose()  # loop-bound asyncpg pool, see process_menu_task

    asyncio.run(run())


@celery_app.task(name="refresh_currency_rates", autoretry_for=(Exception,), retry_backoff=60,
                 max_retries=5)
def refresh_currency_rates_task() -> None:
    """Pull the daily EUR-based rates from Frankfurter (frankfurter.dev — free,
    no key, backed by the ECB reference fixing) and upsert the currencies
    table. Scheduled by beat (see celery_app); retries with backoff since the
    next natural attempt would otherwise be a day away.
    """
    import httpx

    from app.db import SessionLocal, engine
    from app.services.currencies import CurrencyService

    async def run() -> None:
        try:
            async with httpx.AsyncClient(base_url=FRANKFURTER_BASE, timeout=15) as http:
                latest = (await http.get("/latest", params={"base": "EUR"})).raise_for_status()
                currencies = (await http.get("/currencies")).raise_for_status()
            names: dict[str, str] = currencies.json()
            rates = {code: Decimal(str(r)) for code, r in latest.json()["rates"].items()}
            rates["EUR"] = Decimal(1)  # the feed omits the base itself

            async with SessionLocal() as session:
                count = await CurrencyService(session).upsert_rates(rates, names)
            logger.info("refreshed %d currency rates (date %s)", count, latest.json()["date"])
        finally:
            await engine.dispose()  # loop-bound asyncpg pool, see process_menu_task

    asyncio.run(run())
