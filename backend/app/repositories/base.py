from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Shared plumbing for repositories.

    A repository wraps all DB access for one aggregate and returns ORM
    objects. It never controls the transaction: no commit/rollback here.
    Staging (`add`) and `flush` operate within the ambient transaction
    without ending it; the service that owns the unit of work decides when to
    commit (via its session). Nothing above this layer touches the session
    directly except that transaction boundary.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        """Emit pending SQL (e.g. to get a generated id) without committing."""
        await self.session.flush()
