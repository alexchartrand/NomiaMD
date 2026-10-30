"""Deletes audit events past retention: they hold IP addresses, so the whole row goes."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb import AuditEventRepository


class AuditEventPurge:
    def __init__(self, session: AsyncSession) -> None:
        self._events = AuditEventRepository(session)

    async def count_due(self, before: datetime) -> int:
        return await self._events.count_before(before)

    async def purge(self, before: datetime) -> int:
        return await self._events.delete_before(before)
