"""Celery instance — broker is Redis, tasks live in app/tasks.py.

Worker (see docker-compose `worker` service):

    celery -A app.celery_app worker --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("tasted", broker=settings.redis_url, include=["app.tasks"])

celery_app.conf.update(
    # Fire-and-forget: progress is observable in the DB (the client polls the
    # menu), so nobody reads task results — don't store them.
    task_ignore_result=True,
    # Re-deliver if a worker dies mid-task; process_menu only claims `new`
    # scans (new -> processing is atomic), so a duplicate run is harmless.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="Europe/Berlin",  # ECB reference rates are fixed ~16:00 CET
    beat_schedule={
        # Daily FX refresh, shortly after the ECB fixing is published.
        "refresh-currency-rates": {
            "task": "refresh_currency_rates",
            "schedule": crontab(hour=16, minute=30),
        },
        # Recover menus stuck mid-processing (worker died holding the claim).
        "reschedule-stuck-menus": {
            "task": "reschedule_stuck_menus",
            "schedule": 300.0,  # every 5 minutes
        },
        # Fold votes into displayed spice/price values — voting itself never
        # moves a value, this is the only place levels shift.
        "recalculate-dish-attributes": {
            "task": "recalculate_dish_attributes",
            "schedule": 900.0,  # every 15 minutes
        },
    },
)
