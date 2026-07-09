"""Manual end-to-end exercise of the menu pipeline (stub AI, live DB).

Run twice to see both paths:
  1st run: every item misses the cache -> enrichment -> ingest
  2nd run: every item hits the cache -> ready without enrichment

    uv run python -m scripts.try_pipeline            # pipeline runs in-process
    uv run python -m scripts.try_pipeline --celery   # enqueue to a real worker

--celery needs the compose stack up (redis + worker) and mimics production:
this process only creates the menu and enqueues; the worker does the rest
while we poll the DB exactly like the mobile app polls the API.
"""

import asyncio
import sys

from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import Dish
from app.schemas import DishOut
from app.services.menus import MenuService, PhotoUpload
from app.services.processing import MenuProcessor
from app.tasks import schedule_menu_processing

POLL_INTERVAL_S = 1.5  # same cadence as the mobile app
POLL_ATTEMPTS = 40


async def wait_until_complete(menu_id) -> None:
    for _ in range(POLL_ATTEMPTS):
        async with SessionLocal() as session:
            menu = await MenuService(session).get(menu_id)
            if all(s.status == "complete" for s in menu.scans):
                return
        await asyncio.sleep(POLL_INTERVAL_S)
    raise TimeoutError("worker did not finish in time — is `docker compose up worker` running?")


async def main() -> None:
    use_celery = "--celery" in sys.argv

    async with SessionLocal() as session:
        menus = MenuService(session)
        menu = await menus.create_with_photos(
            [PhotoUpload(data=b"fake-page-1", content_type="image/jpeg")],
            name="Cervejaria Brasão",
        )
        print(f"created menu {menu.id} with {len(menu.scans)} scan(s)")
        for scan in menu.scans:
            print(f"  scan {scan.id}: status={scan.status} path={scan.image_path}")

    # What the endpoint will do after responding:
    if use_celery:
        schedule_menu_processing(menu.id)
        print("enqueued to celery, polling...")
        await wait_until_complete(menu.id)
    else:
        await MenuProcessor().process_menu(menu.id)

    async with SessionLocal() as session:
        menus = MenuService(session)
        menu = await menus.get(menu.id)
        print("after processing:")
        for scan in menu.scans:
            print(f"  scan {scan.id}: status={scan.status}")
        for item in menus.combined_items(menu):
            print(
                f"    item #{item.position} {item.original_name!r}: {item.status}"
                f" price={item.menu_price} {item.menu_price_currency}"
                f" dish_id={item.dish_id}"
            )
            if item.dish is not None:
                out = DishOut.from_orm_dish(item.dish)
                print(
                    f"      -> {out.canonical_name}: spice={out.info.spice_level}"
                    f" price_level={out.info.price_level}"
                    f" allergens={[(a.name, a.probability) for a in out.info.allergens]}"
                )
        total = (await session.execute(select(func.count()).select_from(Dish))).scalar_one()
        print(f"dishes in cache: {total}")

    await engine.dispose()


asyncio.run(main())
