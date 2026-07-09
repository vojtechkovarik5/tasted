"""Integration tests for the /questions routes (app/routers/questions.py) —
the "My questions" page behind Settings:

  * GET    /questions             — the saved list, in order
  * POST   /questions             — append one
  * PUT    /questions/order       — persist a drag-reorder
  * DELETE /questions/{id}        — remove one
  * GET    /questions/suggestions — LLM suggestions from the watch list

Auth runs in fake mode (no CLERK_JWKS_URL): `Bearer alice` resolves to user
"alice" — see app/auth.py. No OPENAI_API_KEY is set in tests, so suggestions
come from the deterministic StubQuestionAI (one templated question per active
watch chip) — see app/services/ai.py.
"""

from __future__ import annotations

import uuid

from app.domain import Preferences, WatchChip

ALICE = {"Authorization": "Bearer alice"}
BOB = {"Authorization": "Bearer bob"}


async def _add(client, text: str, headers=ALICE) -> dict:
    resp = await client.post("/questions", json={"text": text}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _texts(client, headers=ALICE) -> list[str]:
    resp = await client.get("/questions", headers=headers)
    assert resp.status_code == 200
    return [q["text"] for q in resp.json()]


class TestListQuestions:
    async def test_new_user_has_no_questions(self, client):
        resp = await client.get("/questions", headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_questions_are_per_user(self, client):
        await _add(client, "Is this gluten-free?", ALICE)

        assert await _texts(client, BOB) == []


class TestAddQuestion:
    async def test_returns_the_saved_question(self, client):
        body = await _add(client, "Is this dish gluten-free?")

        assert body["text"] == "Is this dish gluten-free?"
        uuid.UUID(body["id"])  # a real id the client can delete/reorder by

    async def test_appends_in_order(self, client):
        await _add(client, "first")
        await _add(client, "second")
        await _add(client, "third")

        assert await _texts(client) == ["first", "second", "third"]

    async def test_strips_surrounding_whitespace(self, client):
        body = await _add(client, "  Is there meat in the broth?  ")

        assert body["text"] == "Is there meat in the broth?"

    async def test_rejects_blank_text(self, client):
        resp = await client.post("/questions", json={"text": "   "}, headers=ALICE)

        assert resp.status_code == 422

    async def test_rejects_text_over_500_chars(self, client):
        resp = await client.post("/questions", json={"text": "x" * 501}, headers=ALICE)

        assert resp.status_code == 422


class TestDeleteQuestion:
    async def test_deletes_and_list_shrinks(self, client):
        kept = await _add(client, "keep me")
        doomed = await _add(client, "delete me")

        resp = await client.delete(f"/questions/{doomed['id']}", headers=ALICE)

        assert resp.status_code == 204
        assert await _texts(client) == [kept["text"]]

    async def test_unknown_id_is_404(self, client):
        resp = await client.delete(f"/questions/{uuid.uuid4()}", headers=ALICE)

        assert resp.status_code == 404

    async def test_cannot_delete_another_users_question(self, client):
        alices = await _add(client, "mine", ALICE)

        resp = await client.delete(f"/questions/{alices['id']}", headers=BOB)

        # 404 (not 403) so ids can't be probed across users.
        assert resp.status_code == 404
        assert await _texts(client, ALICE) == ["mine"]

    async def test_appending_after_a_delete_keeps_order(self, client):
        await _add(client, "a")
        b = await _add(client, "b")
        await _add(client, "c")

        await client.delete(f"/questions/{b['id']}", headers=ALICE)
        await _add(client, "d")

        assert await _texts(client) == ["a", "c", "d"]


class TestReorderQuestions:
    async def test_reorders_and_persists(self, client):
        first = await _add(client, "first")
        second = await _add(client, "second")
        third = await _add(client, "third")

        new_order = [third["id"], first["id"], second["id"]]
        resp = await client.put("/questions/order", json={"ids": new_order}, headers=ALICE)

        assert resp.status_code == 200
        assert [q["id"] for q in resp.json()] == new_order
        # Round-trips on the next read (what the sheet will show).
        assert await _texts(client) == ["third", "first", "second"]

    async def test_rejects_partial_list(self, client):
        first = await _add(client, "first")
        await _add(client, "second")

        resp = await client.put("/questions/order", json={"ids": [first["id"]]}, headers=ALICE)

        assert resp.status_code == 422

    async def test_rejects_foreign_or_unknown_ids(self, client):
        await _add(client, "only one")

        resp = await client.put(
            "/questions/order", json={"ids": [str(uuid.uuid4())]}, headers=ALICE
        )

        assert resp.status_code == 422

    async def test_cannot_reorder_with_another_users_ids(self, client):
        alices = await _add(client, "alice's", ALICE)

        resp = await client.put("/questions/order", json={"ids": [alices["id"]]}, headers=BOB)

        assert resp.status_code == 422


class TestSuggestions:
    """GET /questions/suggestions with the StubQuestionAI: one templated
    question per active watch chip ("Does this dish contain {key}?" for
    allergens, "Can this be made {key}?" for dietary)."""

    async def test_seeded_from_default_watch_list(self, client):
        # Fresh users watch gluten + vegetarian by default (Preferences).
        resp = await client.get("/questions/suggestions", headers=ALICE)

        assert resp.status_code == 200
        assert resp.json() == {
            "based_on": ["gluten", "vegetarian"],
            "questions": [
                "Does this dish contain gluten?",
                "Can this be made vegetarian?",
            ],
        }

    async def test_follows_the_watch_list(self, client):
        prefs = Preferences(
            watch_list=[
                WatchChip(key="pork", kind="allergen"),
                WatchChip(key="milk", kind="allergen"),
            ]
        )
        await client.put("/preferences", json=prefs.model_dump(mode="json"), headers=ALICE)

        resp = await client.get("/questions/suggestions", headers=ALICE)

        assert resp.json()["based_on"] == ["pork", "milk"]
        assert resp.json()["questions"] == [
            "Does this dish contain pork?",
            "Does this dish contain milk?",
        ]

    async def test_ignores_chips_toggled_off(self, client):
        prefs = Preferences(
            watch_list=[
                WatchChip(key="gluten", kind="allergen", on=False),
                WatchChip(key="vegetarian", kind="dietary"),
            ]
        )
        await client.put("/preferences", json=prefs.model_dump(mode="json"), headers=ALICE)

        resp = await client.get("/questions/suggestions", headers=ALICE)

        assert resp.json() == {
            "based_on": ["vegetarian"],
            "questions": ["Can this be made vegetarian?"],
        }

    async def test_empty_watch_list_means_no_suggestions(self, client):
        prefs = Preferences(watch_list=[])
        await client.put("/preferences", json=prefs.model_dump(mode="json"), headers=ALICE)

        resp = await client.get("/questions/suggestions", headers=ALICE)

        assert resp.json() == {"based_on": [], "questions": []}

    async def test_already_saved_questions_are_not_suggested(self, client):
        await _add(client, "Does this dish contain gluten?")

        resp = await client.get("/questions/suggestions", headers=ALICE)

        assert resp.json()["questions"] == ["Can this be made vegetarian?"]
