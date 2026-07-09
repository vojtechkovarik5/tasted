"""Integration tests for the dish endpoints (app/routers/dishes.py) and the
vote/ingest logic in app/services/dishes.py.

  * GET  /dishes/{id}              — dish detail
  * POST /dishes/{id}/vote/{target} — nudge spice/price (one vote per user)
  * POST /dishes/{id}/photo         — user photo upload (pending moderation)

There is deliberately no create/list dish endpoint — dishes are born in the AI
ingest pipeline — so we seed them via `DishService.create` (the same path the
pipeline uses) and read them back over HTTP.

Scored attributes round-trip through a shared 0-100 scale:
  spice/price value = level * 20   (level 1.0 → 20, back to 1.0)
  allergen/dietary value = round(probability * 100)
A vote never moves the value directly — the periodic recalculation applies
value = base_value ± `VOTE_STEP` * net votes (see services/dishes.py).

Auth is fake mode: `Authorization: Bearer alice` resolves to the user with
clerk id "alice" (created lazily), so votes are attributable per user.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select

from app.domain import Allergen, DietaryFlag, DishInfo
from app.models import EMBEDDING_DIM, DishPhoto
from app.services.dishes import VOTE_STEP, DishService, get_dish_service


class _InMemoryStorage:
    """Captures uploads in memory so photo tests don't touch disk/S3."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self.objects[key] = data
        return key

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    def public_url(self, key: str) -> str:
        return f"/uploads/{key}"


def _dish_info(name: str = "Francesinha", *, price_level: float | None = 3.0) -> DishInfo:
    return DishInfo(
        original_name=name,
        description=f"{name} — a Porto classic.",
        summary=f"{name} summary",
        origin="Porto",
        allergens=[Allergen(name="gluten", probability=0.99)],
        dietary=[DietaryFlag(name="vegetarian", probability=0.02)],
        spice_level=1.0,  # -> attribute value 20
        price_level=price_level,  # 3.0 -> value 60
    )


async def _seed_dish(db_session, info: DishInfo | None = None) -> uuid.UUID:
    """Ingest a dish through the production path; return its id."""
    dish = await DishService(db_session).create(info or _dish_info(), region="Porto")
    return dish.id


@pytest_asyncio.fixture
async def dish_storage(app_with_overrides, db_session) -> _InMemoryStorage:
    """Route dish photo uploads through in-memory storage."""
    store = _InMemoryStorage()

    def _get_dish_service() -> DishService:
        return DishService(db_session, storage=store)

    app_with_overrides.dependency_overrides[get_dish_service] = _get_dish_service
    return store


ALICE = {"Authorization": "Bearer alice"}
BOB = {"Authorization": "Bearer bob"}


# --------------------------------------------------------------------------
# GET /dishes/{id}
# --------------------------------------------------------------------------


class TestGetDish:
    async def test_returns_dish_detail_with_merged_scores(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        resp = await client.get(f"/dishes/{dish_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["canonical_name"] == "Francesinha"
        assert body["region"] == "Porto"
        info = body["info"]
        assert info["description"] == "Francesinha — a Porto classic."
        # Scored fields come back from dish_attributes, not the JSONB payload.
        assert info["spice_level"] == 1.0
        assert info["price_level"] == 3.0
        # `label` is the catalog-localized display name (English fallback).
        assert info["allergens"] == [
            {"name": "gluten", "probability": 0.99, "label": "gluten"}
        ]
        assert info["dietary"] == [
            {"name": "vegetarian", "probability": 0.02, "label": "vegetarian"}
        ]
        assert body["photos"] == []

    async def test_unknown_dish_is_404(self, client):
        resp = await client.get(f"/dishes/{uuid.uuid4()}")

        assert resp.status_code == 404

    async def test_only_moderated_photos_are_public(self, client, db_session):
        dish_id = await _seed_dish(db_session)
        db_session.add_all(
            [
                DishPhoto(dish_id=dish_id, url="/uploads/ok.jpg", source="ai", status="active"),
                DishPhoto(
                    dish_id=dish_id,
                    url="/uploads/pending.jpg",
                    source="user",
                    status="pending_moderation",
                ),
            ]
        )
        await db_session.flush()

        resp = await client.get(f"/dishes/{dish_id}")

        assert resp.json()["photos"] == [{"url": "/uploads/ok.jpg", "source": "ai"}]


# --------------------------------------------------------------------------
# POST /dishes/{id}/vote/{target}
# --------------------------------------------------------------------------


class TestVote:
    async def _spice(self, client, dish_id) -> float:
        resp = await client.get(f"/dishes/{dish_id}")
        return resp.json()["info"]["spice_level"]

    async def _recalc(self, db_session) -> None:
        """What the periodic beat task runs (tasks.py wraps this)."""
        await DishService(db_session).recalculate_attributes()

    async def test_vote_does_not_move_the_value(self, client, db_session):
        dish_id = await _seed_dish(db_session)  # spice starts at value 20 (1.0)

        resp = await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == {"accepted": True}
        # Votes are only folded in by the periodic recalculation.
        assert await self._spice(client, dish_id) == 1.0

    async def test_recalculation_folds_votes_into_the_value(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await self._recalc(db_session)

        # base 20 + VOTE_STEP -> 24, rendered as 24/20 = 1.2
        assert await self._spice(client, dish_id) == (20 + VOTE_STEP) / 20

    async def test_repeat_vote_is_idempotent(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await self._recalc(db_session)

        # Same user, same direction — one vote, counted once.
        assert await self._spice(client, dish_id) == (20 + VOTE_STEP) / 20

    async def test_flipping_a_vote_reverses_it(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "down"}, headers=ALICE)
        await self._recalc(db_session)

        # The flip replaces the vote: net -1 from the SAME baseline (not a
        # double-step swing off a moved value).
        assert await self._spice(client, dish_id) == (20 - VOTE_STEP) / 20

    async def test_votes_from_different_users_accumulate(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=BOB)
        await self._recalc(db_session)

        # One step per distinct user, all anchored on the baseline.
        assert await self._spice(client, dish_id) == (20 + 2 * VOTE_STEP) / 20

    async def test_recalculation_is_stable_across_runs(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        await self._recalc(db_session)
        await self._recalc(db_session)

        # Re-running without new votes must not drift the value.
        assert await self._spice(client, dish_id) == (20 + VOTE_STEP) / 20

    async def test_my_votes_reflect_what_i_pressed(self, client, db_session):
        # Levels only shift on recalculation, so the UI restores the pressed
        # arrow from GET /dishes/{id}/votes rather than from the value.
        dish_id = await _seed_dish(db_session)

        resp = await client.get(f"/dishes/{dish_id}/votes", headers=ALICE)
        assert resp.status_code == 200
        assert resp.json() == {"spice": None, "price": None}

        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "up"}, headers=ALICE)
        resp = await client.get(f"/dishes/{dish_id}/votes", headers=ALICE)
        assert resp.json() == {"spice": "up", "price": None}

        # Changing your mind flips the stored vote...
        await client.post(f"/dishes/{dish_id}/vote/spice", json={"direction": "down"}, headers=ALICE)
        resp = await client.get(f"/dishes/{dish_id}/votes", headers=ALICE)
        assert resp.json() == {"spice": "down", "price": None}

        # ...and votes are per user: bob still sees none of alice's.
        resp = await client.get(f"/dishes/{dish_id}/votes", headers=BOB)
        assert resp.json() == {"spice": None, "price": None}

    async def test_my_votes_unknown_dish_is_404(self, client):
        resp = await client.get(f"/dishes/{uuid.uuid4()}/votes", headers=ALICE)
        assert resp.status_code == 404

    async def test_vote_creates_missing_attribute_at_midpoint(self, client, db_session):
        # A dish ingested without a price (price_level=None) has no price row;
        # the first vote seeds it at the neutral 50 (also its baseline), and
        # the vote itself only lands on recalculation.
        dish_id = await _seed_dish(db_session, _dish_info(price_level=None))

        await client.post(f"/dishes/{dish_id}/vote/price", json={"direction": "up"}, headers=ALICE)

        resp = await client.get(f"/dishes/{dish_id}")
        assert resp.json()["info"]["price_level"] == 50 / 20

        await self._recalc(db_session)
        resp = await client.get(f"/dishes/{dish_id}")
        assert resp.json()["info"]["price_level"] == (50 + VOTE_STEP) / 20

    async def test_vote_on_unknown_dish_is_404(self, client):
        resp = await client.post(
            f"/dishes/{uuid.uuid4()}/vote/spice", json={"direction": "up"}, headers=ALICE
        )

        assert resp.status_code == 404

    async def test_invalid_target_is_422(self, client, db_session):
        dish_id = await _seed_dish(db_session)

        resp = await client.post(
            f"/dishes/{dish_id}/vote/sweetness", json={"direction": "up"}, headers=ALICE
        )

        assert resp.status_code == 422  # not a VoteTarget enum member


# --------------------------------------------------------------------------
# POST /dishes/{id}/photo
# --------------------------------------------------------------------------


class TestUploadPhoto:
    async def test_accepts_an_image_and_stores_it_pending(self, client, dish_storage, db_session):
        dish_id = await _seed_dish(db_session)

        resp = await client.post(
            f"/dishes/{dish_id}/photo",
            files={"photo": ("dish.jpg", b"\xff\xd8\xffjpeg", "image/jpeg")},
            headers=ALICE,
        )

        assert resp.status_code == 200
        assert resp.json() == {"accepted": True, "status": "pending_moderation"}
        assert len(dish_storage.objects) == 1

        rows = (
            await db_session.execute(select(DishPhoto).where(DishPhoto.dish_id == dish_id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == "user"
        assert rows[0].status == "pending_moderation"

    async def test_uploaded_photo_is_hidden_until_moderated(self, client, dish_storage, db_session):
        dish_id = await _seed_dish(db_session)

        await client.post(
            f"/dishes/{dish_id}/photo",
            files={"photo": ("dish.jpg", b"\xff\xd8\xffjpeg", "image/jpeg")},
            headers=ALICE,
        )

        detail = await client.get(f"/dishes/{dish_id}")
        assert detail.json()["photos"] == []  # still pending moderation

    async def test_rejects_non_image_upload(self, client, dish_storage, db_session):
        dish_id = await _seed_dish(db_session)

        resp = await client.post(
            f"/dishes/{dish_id}/photo",
            files={"photo": ("notes.txt", b"hello", "text/plain")},
            headers=ALICE,
        )

        assert resp.status_code == 422
        assert dish_storage.objects == {}  # rejected before storage

    async def test_photo_for_unknown_dish_is_404(self, client, dish_storage):
        resp = await client.post(
            f"/dishes/{uuid.uuid4()}/photo",
            files={"photo": ("dish.jpg", b"\xff\xd8\xffjpeg", "image/jpeg")},
            headers=ALICE,
        )

        assert resp.status_code == 404


# --------------------------------------------------------------------------
# DishService directly — the ingest half (attribute fanning + cache lookup)
# --------------------------------------------------------------------------


class TestDishServiceIngest:
    async def test_create_fans_scores_into_attribute_rows(self, db_session):
        service = DishService(db_session)

        dish = await service.create(_dish_info())

        attrs = {(a.kind, a.key): a.value for a in dish.attributes}
        assert attrs[("allergen", "gluten")] == 99
        assert attrs[("dietary", "vegetarian")] == 2
        assert attrs[("spice", None)] == 20
        assert attrs[("price", None)] == 60
        # Descriptive payload keeps prose but not the scored fields.
        assert "description" in dish.data
        assert "allergens" not in dish.data
        assert "spice_level" not in dish.data

    async def test_find_similar_hits_same_embedding_and_misses_far_ones(self, db_session):
        service = DishService(db_session)
        embedding = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        dish = await service.create(_dish_info(), embedding=embedding)

        found = await service.find_similar(embedding)
        assert found is not None
        hit, confidence = found
        assert hit.id == dish.id
        assert confidence == 100  # identical embedding -> distance 0

        orthogonal = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
        assert await service.find_similar(orthogonal) is None
