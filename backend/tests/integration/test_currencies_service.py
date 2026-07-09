"""Integration tests for CurrencyService against a real database.

The service is where the interesting logic lives — cross-rate conversion
through the EUR base and the daily rate-feed upsert — so these exercise it
directly with a live session rather than over HTTP.
"""

from __future__ import annotations

from decimal import Decimal

import pytest_asyncio

from app.models import Currency
from app.services.currencies import CurrencyService


@pytest_asyncio.fixture
async def service(db_session) -> CurrencyService:
    return CurrencyService(db_session)


@pytest_asyncio.fixture
async def seed_currencies(db_session) -> None:
    rows = [
        Currency(code="EUR", name="Euro", symbol="€", rate_per_eur=Decimal("1")),
        Currency(code="USD", name="US Dollar", symbol="$", rate_per_eur=Decimal("1.10")),
        Currency(code="CZK", name="Czech koruna", symbol="Kč", rate_per_eur=Decimal("25")),
    ]
    db_session.add_all(rows)
    await db_session.flush()


class TestConvert:
    async def test_from_base_currency(self, service, seed_currencies):
        # 10 EUR -> CZK at 25 CZK/EUR
        assert await service.convert(Decimal("10"), "EUR", "CZK") == Decimal("250")

    async def test_to_base_currency(self, service, seed_currencies):
        # 250 CZK -> EUR
        assert await service.convert(Decimal("250"), "CZK", "EUR") == Decimal("10")

    async def test_cross_rate_through_eur(self, service, seed_currencies):
        # 25 CZK == 1 EUR == 1.10 USD
        assert await service.convert(Decimal("25"), "CZK", "USD") == Decimal("1.10")

    async def test_same_currency_is_identity(self, service, seed_currencies):
        assert await service.convert(Decimal("42"), "USD", "USD") == Decimal("42")

    async def test_code_is_case_insensitive(self, service, seed_currencies):
        assert await service.convert(Decimal("10"), "eur", "czk") == Decimal("250")

    async def test_unknown_source_returns_none(self, service, seed_currencies):
        assert await service.convert(Decimal("10"), "XXX", "EUR") is None

    async def test_unknown_target_returns_none(self, service, seed_currencies):
        assert await service.convert(Decimal("10"), "EUR", "XXX") is None


class TestUpsertRates:
    async def test_updates_existing_rate_and_name(self, service, db_session, seed_currencies):
        count = await service.upsert_rates(
            rates={"USD": Decimal("1.20")},
            names={"USD": "United States dollar"},
        )

        assert count == 1
        usd = await service.get("USD")
        assert usd.rate_per_eur == Decimal("1.20")
        assert usd.name == "United States dollar"

    async def test_preserves_symbol_on_update(self, service, seed_currencies):
        # The rate feed doesn't carry symbols — upsert must leave them alone.
        await service.upsert_rates(rates={"USD": Decimal("1.20")}, names={"USD": "US Dollar"})

        assert (await service.get("USD")).symbol == "$"

    async def test_inserts_new_currency(self, service, seed_currencies):
        await service.upsert_rates(
            rates={"PLN": Decimal("4.30")},
            names={"PLN": "Polish zloty"},
        )

        pln = await service.get("PLN")
        assert pln is not None
        assert pln.rate_per_eur == Decimal("4.30")
        assert pln.name == "Polish zloty"
        assert pln.symbol is None  # not supplied by the feed

    async def test_falls_back_to_code_when_name_missing(self, service, seed_currencies):
        await service.upsert_rates(rates={"SEK": Decimal("11.5")}, names={})

        assert (await service.get("SEK")).name == "SEK"

    async def test_convert_reflects_upserted_rate(self, service, seed_currencies):
        await service.upsert_rates(rates={"USD": Decimal("2")}, names={"USD": "US Dollar"})

        # 1 EUR now buys 2 USD.
        assert await service.convert(Decimal("1"), "EUR", "USD") == Decimal("2")
