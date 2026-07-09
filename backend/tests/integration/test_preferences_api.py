"""Integration tests for the /preferences language routes
(app/routers/preferences.py):

  * GET  /preferences/languages — the "My language" picker feed
  * POST /preferences/language  — set the authed user's language

Auth runs in fake mode (no CLERK_JWKS_URL): a missing token resolves to the
fixed dev user, and `-H "Authorization: Bearer alice"` resolves to user
"alice" — see app/auth.py.
"""

from __future__ import annotations


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
