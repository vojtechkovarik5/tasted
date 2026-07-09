"""Integration tests for the menu endpoints (app/routers/menus.py):

  * POST /menus            — create a menu from photo pages
  * GET  /menus            — the user's menu history
  * GET  /menus/{menu_id}  — poll one menu

Run against a real database. Two things about the environment under test:

  * `create_menu` enqueues the Celery pipeline via `process_menu_task.delay`.
    We stub `.delay` (autouse `stub_process_task`) so no broker is needed and
    no AI processing runs — we're testing the create/read HTTP surface, not
    the worker.
  * `create_with_photos` writes the uploaded bytes to object storage. We swap
    in an in-memory storage (the `menu_service` fixture) so tests don't touch
    disk or S3.

Auth is in fake mode (no CLERK_JWKS_URL): no header → anonymous;
`Authorization: Bearer alice` → the user whose clerk id is "alice".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from app.models import Currency, Menu, Scan, ScanItem, User
from app.services.menus import MenuService, get_menu_service


class InMemoryStorage:
    """A Storage backend that keeps bytes in a dict — no disk, no S3."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self.objects[key] = data
        return key

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    def public_url(self, key: str) -> str:
        return f"/uploads/{key}"


@pytest.fixture(autouse=True)
def stub_process_task(monkeypatch) -> MagicMock:
    """Neutralize the Celery dispatch in create_menu so no broker is hit."""
    import app.routers.menus as menus_router

    delay = MagicMock()
    monkeypatch.setattr(menus_router.process_menu_task, "delay", delay)
    return delay


@pytest_asyncio.fixture
async def storage(app_with_overrides, db_session) -> InMemoryStorage:
    """In-memory storage, injected by overriding the MenuService dependency."""
    store = InMemoryStorage()

    def _get_menu_service() -> MenuService:
        return MenuService(db_session, storage=store)

    app_with_overrides.dependency_overrides[get_menu_service] = _get_menu_service
    return store


@pytest_asyncio.fixture
async def make_user(db_session):
    """Insert a user with a given clerk id (matches `Bearer <clerk_id>`)."""

    async def _make(clerk_id: str = "alice") -> User:
        user = User(clerk_user_id=clerk_id)
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


def _photo(name: str = "page.jpg", data: bytes = b"\xff\xd8\xff\xe0jpegbytes"):
    """An httpx multipart file tuple for the `photos` form field."""
    return ("photos", (name, data, "image/jpeg"))


async def _seed_menu(
    db_session,
    *,
    user_id: uuid.UUID | None = None,
    name: str | None = None,
    created_at: datetime | None = None,
    scans: list[Scan] | None = None,
    language: str | None = None,
) -> Menu:
    menu = Menu(id=uuid.uuid4(), user_id=user_id, name=name, language=language)
    if created_at is not None:
        menu.created_at = created_at
    menu.scans = scans if scans is not None else []
    db_session.add(menu)
    await db_session.flush()
    return menu


# --------------------------------------------------------------------------
# POST /menus
# --------------------------------------------------------------------------


class TestCreateMenu:
    async def test_creates_anonymous_menu(self, client, storage, db_session):
        resp = await client.post("/menus", files=[_photo()], data={"name": "Café Lisboa"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Café Lisboa"
        assert body["status"] == "processing"  # fresh scan is not complete yet
        assert body["items"] == []
        uuid.UUID(body["id"])  # a real uuid

        # Persisted, unowned, with one stored page.
        menu = await db_session.get(Menu, uuid.UUID(body["id"]))
        assert menu is not None
        assert menu.user_id is None
        assert len(menu.scans) == 1
        assert len(storage.objects) == 1

    async def test_enqueues_processing_task(self, client, storage, stub_process_task):
        resp = await client.post("/menus", files=[_photo()])

        stub_process_task.assert_called_once_with(resp.json()["id"])

    async def test_stores_each_page_as_a_scan(self, client, storage, db_session):
        files = [_photo("p1.jpg"), _photo("p2.jpg"), _photo("p3.jpg")]

        resp = await client.post("/menus", files=files)

        menu = await db_session.get(Menu, uuid.UUID(resp.json()["id"]))
        assert len(menu.scans) == 3
        assert len(storage.objects) == 3

    async def test_owned_when_authenticated(self, client, storage, db_session, make_user):
        alice = await make_user("alice")

        resp = await client.post(
            "/menus", files=[_photo()], headers={"Authorization": "Bearer alice"}
        )

        menu = await db_session.get(Menu, uuid.UUID(resp.json()["id"]))
        assert menu.user_id == alice.id

    async def test_name_is_optional(self, client, storage):
        resp = await client.post("/menus", files=[_photo()])

        assert resp.status_code == 200
        assert resp.json()["name"] is None


# --------------------------------------------------------------------------
# GET /menus
# --------------------------------------------------------------------------


class TestListMenus:
    async def test_anonymous_history_is_empty(self, client):
        resp = await client.get("/menus")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_lists_users_menus_newest_first(self, client, db_session, make_user):
        alice = await make_user("alice")
        now = datetime.now(timezone.utc)
        await _seed_menu(db_session, user_id=alice.id, name="older", created_at=now - timedelta(hours=2))
        await _seed_menu(db_session, user_id=alice.id, name="newer", created_at=now)

        resp = await client.get("/menus", headers={"Authorization": "Bearer alice"})

        assert [m["name"] for m in resp.json()] == ["newer", "older"]

    async def test_history_is_scoped_to_the_user(self, client, db_session, make_user):
        alice = await make_user("alice")
        bob = await make_user("bob")
        await _seed_menu(db_session, user_id=alice.id, name="alice's")
        await _seed_menu(db_session, user_id=bob.id, name="bob's")

        resp = await client.get("/menus", headers={"Authorization": "Bearer bob"})

        assert [m["name"] for m in resp.json()] == ["bob's"]

    async def test_summary_counts_combined_items(self, client, db_session, make_user):
        alice = await make_user("alice")
        scan = Scan(id=uuid.uuid4(), image_path="k", status="complete")
        scan.items = [
            ScanItem(id=uuid.uuid4(), position=0, original_name="Soup", status="ready"),
            ScanItem(id=uuid.uuid4(), position=1, original_name="Bread", status="pending"),
        ]
        await _seed_menu(db_session, user_id=alice.id, name="Dinner", scans=[scan])

        resp = await client.get("/menus", headers={"Authorization": "Bearer alice"})

        row = resp.json()[0]
        assert row["item_count"] == 2  # both items counted, across the page
        # Menu status tracks scan (page) completion, not per-item enrichment:
        # the one page is done, so the menu reads complete.
        assert row["status"] == "complete"


# --------------------------------------------------------------------------
# GET /menus/{menu_id}
# --------------------------------------------------------------------------


class TestGetMenu:
    async def test_anonymous_menu_readable_by_id(self, client, db_session):
        menu = await _seed_menu(db_session, user_id=None, name="Walk-in")

        resp = await client.get(f"/menus/{menu.id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(menu.id)

    async def test_includes_menu_language(self, client, db_session):
        # Stored during extraction; the ask-staff sheet uses it as the
        # translation target.
        menu = await _seed_menu(db_session, language="pt")

        resp = await client.get(f"/menus/{menu.id}")

        assert resp.json()["language"] == "pt"

    async def test_language_is_null_for_older_menus(self, client, db_session):
        menu = await _seed_menu(db_session)  # scanned before languages existed

        resp = await client.get(f"/menus/{menu.id}")

        assert resp.json()["language"] is None

    async def test_owner_can_read_own_menu(self, client, db_session, make_user):
        alice = await make_user("alice")
        menu = await _seed_menu(db_session, user_id=alice.id, name="Mine")

        resp = await client.get(
            f"/menus/{menu.id}", headers={"Authorization": "Bearer alice"}
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Mine"

    async def test_other_user_cannot_read_owned_menu(self, client, db_session, make_user):
        alice = await make_user("alice")
        await make_user("bob")
        menu = await _seed_menu(db_session, user_id=alice.id)

        resp = await client.get(
            f"/menus/{menu.id}", headers={"Authorization": "Bearer bob"}
        )

        assert resp.status_code == 404

    async def test_anonymous_cannot_read_owned_menu(self, client, db_session, make_user):
        alice = await make_user("alice")
        menu = await _seed_menu(db_session, user_id=alice.id)

        resp = await client.get(f"/menus/{menu.id}")

        assert resp.status_code == 404

    async def test_missing_menu_is_404(self, client):
        resp = await client.get(f"/menus/{uuid.uuid4()}")

        assert resp.status_code == 404

    async def test_returns_items_with_converted_price(self, client, db_session):
        # Item printed in EUR; anonymous target currency is the CZK default.
        db_session.add_all(
            [
                Currency(code="EUR", name="Euro", symbol="€", rate_per_eur=Decimal("1")),
                Currency(code="CZK", name="Czech koruna", symbol="Kč", rate_per_eur=Decimal("25")),
            ]
        )
        scan = Scan(id=uuid.uuid4(), image_path="k", status="complete")
        scan.items = [
            ScanItem(
                id=uuid.uuid4(),
                position=0,
                original_name="Bacalhau à Brás",
                status="ready",
                menu_price=Decimal("10.00"),
                menu_price_currency="EUR",
            )
        ]
        menu = await _seed_menu(db_session, user_id=None, scans=[scan])

        resp = await client.get(f"/menus/{menu.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "complete"
        item = body["items"][0]
        assert item["original_name"] == "Bacalhau à Brás"
        assert item["status"] == "ready"
        assert item["menu_price"] == {"amount": 10.0, "currency": "EUR"}
        assert item["approx_price"] == {"amount": 250.0, "currency": "CZK"}
        assert item["dish"] is None
