"""Integration tests for the /currencies HTTP endpoints.

Covers the two routes in app/routers/currencies.py against a real database:
  * GET  /currencies  — the "My currency" dropdown feed
  * POST /currencies  — set the authed user's display currency

Auth runs in fake mode (no CLERK_JWKS_URL): a missing token resolves to the
fixed dev user, and `-H "Authorization: Bearer alice"` resolves to user
"alice" — see app/auth.py.
"""

from __future__ import annotations

from decimal import Decimal

import pytest_asyncio

from app.models import Currency


@pytest_asyncio.fixture
async def seed_currencies(db_session) -> dict[str, Currency]:
    """A small, known currency set so assertions don't depend on the seed
    migration. Rates are units per 1 EUR (EUR is the base, so 1)."""
    rows = [
        Currency(code="EUR", name="Euro", symbol="€", rate_per_eur=Decimal("1")),
        Currency(code="USD", name="US Dollar", symbol="$", rate_per_eur=Decimal("1.10")),
        Currency(code="CZK", name="Czech koruna", symbol="Kč", rate_per_eur=Decimal("25")),
        Currency(code="GBP", name="Pound sterling", symbol="£", rate_per_eur=Decimal("0.85")),
    ]
    db_session.add_all(rows)
    await db_session.flush()
    return {c.code: c for c in rows}


class TestListCurrencies:
    async def test_returns_seeded_currencies_ordered_by_code(self, client, seed_currencies):
        resp = await client.get("/currencies")

        assert resp.status_code == 200
        body = resp.json()
        assert [c["code"] for c in body] == ["CZK", "EUR", "GBP", "USD"]  # alphabetical

    async def test_currency_shape_matches_schema(self, client, seed_currencies):
        resp = await client.get("/currencies")

        usd = next(c for c in resp.json() if c["code"] == "USD")
        assert usd == {
            "code": "USD",
            "name": "US Dollar",
            "symbol": "$",
            "rate_per_eur": 1.10,
        }

    async def test_empty_when_no_currencies_seeded(self, client):
        resp = await client.get("/currencies")

        assert resp.status_code == 200
        assert resp.json() == []


class TestSetMyCurrency:
    async def test_sets_supported_currency(self, client, seed_currencies):
        resp = await client.post("/currencies", json={"code": "USD"})

        assert resp.status_code == 200
        assert resp.json() == {"code": "USD"}

    async def test_code_is_normalized_to_uppercase(self, client, seed_currencies):
        resp = await client.post("/currencies", json={"code": "usd"})

        assert resp.status_code == 200
        assert resp.json() == {"code": "USD"}

    async def test_rejects_unsupported_currency(self, client, seed_currencies):
        resp = await client.post("/currencies", json={"code": "XYZ"})

        assert resp.status_code == 422
        assert "XYZ" in resp.json()["detail"]

    async def test_selection_persists_on_user_preferences(self, client, seed_currencies):
        # Default currency is CZK (app/domain/preferences.py); switch it.
        await client.post("/currencies", json={"code": "GBP"})

        prefs = await client.get("/preferences")
        assert prefs.status_code == 200
        assert prefs.json()["currency"] == "GBP"

    async def test_selection_is_per_user(self, client, seed_currencies):
        alice = {"Authorization": "Bearer alice"}
        bob = {"Authorization": "Bearer bob"}

        await client.post("/currencies", json={"code": "USD"}, headers=alice)
        await client.post("/currencies", json={"code": "GBP"}, headers=bob)

        assert (await client.get("/preferences", headers=alice)).json()["currency"] == "USD"
        assert (await client.get("/preferences", headers=bob)).json()["currency"] == "GBP"
