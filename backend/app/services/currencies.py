from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionDep
from app.models import Currency
from app.repositories import CurrencyRepository


class CurrencyService:
    def __init__(self, session: AsyncSession):
        self.session = session  # owns the transaction boundary
        self.currencies = CurrencyRepository(session)

    async def list(self) -> list[Currency]:
        """All currencies, alphabetical by code — the dropdown order."""
        return await self.currencies.list()

    async def get(self, code: str) -> Currency | None:
        return await self.currencies.get(code)

    async def convert(self, amount: Decimal, from_code: str, to_code: str) -> Decimal | None:
        """Cross rate through the EUR base (see the Currency model).

        Returns None when either currency is unknown — callers (e.g. the
        approx_price on menu items) degrade to showing only the menu price.
        """
        src = await self.currencies.get(from_code)
        dst = await self.currencies.get(to_code)
        if src is None or dst is None:
            return None
        return amount / src.rate_per_eur * dst.rate_per_eur

    async def upsert_rates(self, rates: dict[str, Decimal], names: dict[str, str]) -> int:
        """Refresh the table from a rate feed (units per 1 EUR, keyed by code).

        Known currencies get rate (and name) updated, new ones inserted;
        `symbol` is left alone (the feed doesn't carry it). Returns the count
        touched. Called by the daily refresh task (app/tasks.py).
        """
        values = [
            {"code": code, "name": names.get(code, code), "rate_per_eur": rate}
            for code, rate in rates.items()
        ]
        await self.currencies.upsert_rates(values)
        await self.session.commit()
        return len(values)


def get_currency_service(session: SessionDep) -> CurrencyService:
    return CurrencyService(session)


CurrencyServiceDep = Annotated[CurrencyService, Depends(get_currency_service)]
