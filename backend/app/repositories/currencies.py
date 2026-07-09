from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import Currency
from app.repositories.base import BaseRepository


class CurrencyRepository(BaseRepository):
    async def list(self) -> list[Currency]:
        stmt = select(Currency).order_by(Currency.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, code: str) -> Currency | None:
        return await self.session.get(Currency, code.upper())

    async def upsert_rates(self, values: list[dict]) -> None:
        """Bulk upsert rows keyed by `code`; refresh rate + name, keep symbol.

        `values` items: {"code", "name", "rate_per_eur"}. Caller commits.
        """
        stmt = insert(Currency).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Currency.code],
            set_={"rate_per_eur": stmt.excluded.rate_per_eur, "name": stmt.excluded.name},
        )
        await self.session.execute(stmt)
