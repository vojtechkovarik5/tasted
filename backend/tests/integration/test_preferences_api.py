"""Integration tests for the /preferences language routes
(app/routers/preferences.py):

  * GET  /preferences/languages — the "My language" picker feed
  * POST /preferences/language  — set the authed user's language

Auth runs in fake mode (no CLERK_JWKS_URL): a missing token resolves to the
fixed dev user, and `-H "Authorization: Bearer alice"` resolves to user
"alice" — see app/auth.py.
"""

from __future__ import annotations

from app.domain import Language, Preferences, WatchChip

ALICE = {"Authorization": "Bearer alice"}
BOB = {"Authorization": "Bearer bob"}


def _custom_prefs() -> Preferences:
    """A fully non-default preferences payload."""
    return Preferences(
        watch_list=[
            WatchChip(key="pork", kind="allergen"),
            WatchChip(key="vegan", kind="dietary", on=False),
        ],
        macros=["carbs", "kcal"],
        section_order=["macros", "restrictions", "spice_price"],
        currency="EUR",
        language=Language.pt,
    )


class TestPreferencesSync:
    """GET/PUT /preferences — the cross-device sync of the whole prefs blob.

    The response model is `Preferences`, so responses compare exactly against
    `Preferences(...).model_dump(mode="json")`.
    """

    async def test_new_user_gets_defaults(self, client):
        resp = await client.get("/preferences", headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == Preferences().model_dump(mode="json")

    async def test_put_replaces_and_persists(self, client):
        prefs = _custom_prefs().model_dump(mode="json")

        put = await client.put("/preferences", json=prefs, headers=ALICE)
        assert put.status_code == 200
        assert put.json() == prefs

        # Round-trips on the next read (the point of the sync).
        get = await client.get("/preferences", headers=ALICE)
        assert get.json() == prefs

    async def test_put_is_last_write_wins(self, client):
        await client.put("/preferences", json=_custom_prefs().model_dump(mode="json"), headers=ALICE)

        # A second PUT fully replaces the first — no merge.
        defaults = Preferences().model_dump(mode="json")
        await client.put("/preferences", json=defaults, headers=ALICE)

        assert (await client.get("/preferences", headers=ALICE)).json() == defaults

    async def test_preferences_are_per_user(self, client):
        await client.put("/preferences", json=_custom_prefs().model_dump(mode="json"), headers=ALICE)

        # Bob never wrote anything — still on defaults.
        assert (await client.get("/preferences", headers=BOB)).json() == Preferences().model_dump(
            mode="json"
        )

    async def test_setting_language_leaves_other_prefs_untouched(self, client):
        # POST /language patches only `language`; the rest stays default.
        await client.post("/preferences/language", json={"code": "fr"}, headers=ALICE)

        expected = Preferences(language=Language.fr).model_dump(mode="json")
        assert (await client.get("/preferences", headers=ALICE)).json() == expected


class TestListLanguages:
    async def test_english_is_first_and_default_shape(self, client):
        resp = await client.get("/preferences/languages")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0] == {"code": "en", "name": "English"}
        # The four the product spec names are all offered.
        codes = {row["code"] for row in body}
        assert {"en", "de", "fr", "es"} <= codes

    async def test_no_auth_required(self, client):
        # The picker is a static allow-list — readable without a token.
        resp = await client.get("/preferences/languages")
        assert resp.status_code == 200


class TestSetMyLanguage:
    async def test_sets_supported_language(self, client):
        resp = await client.post("/preferences/language", json={"code": "de"})

        assert resp.status_code == 200
        assert resp.json() == {"code": "de"}

    async def test_code_is_normalized_to_lowercase(self, client):
        resp = await client.post("/preferences/language", json={"code": "FR"})

        assert resp.status_code == 200
        assert resp.json() == {"code": "fr"}

    async def test_rejects_unsupported_language(self, client):
        resp = await client.post("/preferences/language", json={"code": "xx"})

        assert resp.status_code == 422
        assert "xx" in resp.json()["detail"]

    async def test_selection_persists_on_user_preferences(self, client):
        # Default language is English; switch it.
        await client.post("/preferences/language", json={"code": "es"})

        prefs = await client.get("/preferences")
        assert prefs.status_code == 200
        assert prefs.json()["language"] == "es"

    async def test_default_language_is_english(self, client):
        prefs = await client.get("/preferences")
        assert prefs.json()["language"] == "en"

    async def test_selection_is_per_user(self, client):
        alice = {"Authorization": "Bearer alice"}
        bob = {"Authorization": "Bearer bob"}

        await client.post("/preferences/language", json={"code": "de"}, headers=alice)
        await client.post("/preferences/language", json={"code": "fr"}, headers=bob)

        assert (await client.get("/preferences", headers=alice)).json()["language"] == "de"
        assert (await client.get("/preferences", headers=bob)).json()["language"] == "fr"
