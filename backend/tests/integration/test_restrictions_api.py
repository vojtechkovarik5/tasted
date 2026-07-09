"""Integration tests for the watch-list endpoints (app/routers/restrictions.py):

  * GET/POST /restrictions — allergens & ingredient categories ("gluten", "pork")
  * GET/POST /dietary      — diets the user follows ("vegetarian", "halal")

Both are views over the single ordered `prefs.watch_list`, split by `kind`. A
POST *replaces* the whole list for its kind (the chips UI always posts the full
set) and must leave the other kind alone. GET returns only chips that are `on`.

A brand-new user starts from the `Preferences()` defaults: one allergen chip
("gluten") and one dietary chip ("vegetarian").

Auth is fake mode: `Authorization: Bearer alice` → user "alice"; a missing
token → the fixed dev user.
"""

from __future__ import annotations

from app.domain import Preferences, WatchChip

ALICE = {"Authorization": "Bearer alice"}
BOB = {"Authorization": "Bearer bob"}


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


class TestDefaults:
    async def test_default_restrictions(self, client):
        resp = await client.get("/restrictions", headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == ["gluten"]  # the default allergen chip

    async def test_default_dietary(self, client):
        resp = await client.get("/dietary", headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == ["vegetarian"]  # the default dietary chip


# --------------------------------------------------------------------------
# POST replaces the whole list for its kind
# --------------------------------------------------------------------------


class TestSetRestrictions:
    async def test_set_returns_and_persists(self, client):
        resp = await client.post("/restrictions", json=["gluten", "pork"], headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == ["gluten", "pork"]
        assert (await client.get("/restrictions", headers=ALICE)).json() == ["gluten", "pork"]

    async def test_post_replaces_rather_than_merges(self, client):
        await client.post("/restrictions", json=["gluten", "pork"], headers=ALICE)

        # A later POST is the full set, not an addition.
        await client.post("/restrictions", json=["shellfish"], headers=ALICE)
        assert (await client.get("/restrictions", headers=ALICE)).json() == ["shellfish"]

    async def test_empty_list_clears(self, client):
        await client.post("/restrictions", json=[], headers=ALICE)

        assert (await client.get("/restrictions", headers=ALICE)).json() == []

    async def test_does_not_touch_dietary(self, client):
        await client.post("/restrictions", json=["pork", "shellfish"], headers=ALICE)

        # The other kind is left exactly as it was (still the default).
        assert (await client.get("/dietary", headers=ALICE)).json() == ["vegetarian"]

    async def test_restrictions_are_per_user(self, client):
        await client.post("/restrictions", json=["pork"], headers=ALICE)

        assert (await client.get("/restrictions", headers=BOB)).json() == ["gluten"]


class TestSetDietary:
    async def test_set_returns_and_persists(self, client):
        resp = await client.post("/dietary", json=["vegan", "halal"], headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == ["vegan", "halal"]
        assert (await client.get("/dietary", headers=ALICE)).json() == ["vegan", "halal"]

    async def test_does_not_touch_restrictions(self, client):
        await client.post("/dietary", json=["vegan"], headers=ALICE)

        assert (await client.get("/restrictions", headers=ALICE)).json() == ["gluten"]


# --------------------------------------------------------------------------
# Consistency with the PUT /preferences view of the same data
# --------------------------------------------------------------------------


class TestSharedWatchList:
    async def test_reflects_watch_list_set_via_put_preferences(self, client):
        prefs = Preferences(
            watch_list=[
                WatchChip(key="gluten", kind="allergen", on=False),  # off -> hidden
                WatchChip(key="pork", kind="allergen"),
                WatchChip(key="halal", kind="dietary"),
            ]
        )
        await client.put("/preferences", json=prefs.model_dump(mode="json"), headers=ALICE)

        # GET filters out the `off` chip and splits by kind.
        assert (await client.get("/restrictions", headers=ALICE)).json() == ["pork"]
        assert (await client.get("/dietary", headers=ALICE)).json() == ["halal"]

    async def test_post_shows_up_in_put_preferences_view(self, client):
        await client.post("/restrictions", json=["pork"], headers=ALICE)
        await client.post("/dietary", json=["vegan"], headers=ALICE)

        prefs = (await client.get("/preferences", headers=ALICE)).json()
        chips = {(c["key"], c["kind"], c["on"]) for c in prefs["watch_list"]}
        assert ("pork", "allergen", True) in chips
        assert ("vegan", "dietary", True) in chips
