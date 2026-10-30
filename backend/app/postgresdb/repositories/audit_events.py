"""`audit_events` — the append-only account trail (app/audit/)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select

from app.postgresdb.models import AuditEvent
from app.postgresdb.repositories.base import SessionRepository


@dataclass(frozen=True)
class AuditEventInput:
    action: str
    actor_id: int | None = None
    target_user_id: int | None = None
    details: dict | None = None
    ip: str | None = None


@dataclass(frozen=True)
class AuditEventFilter:
    """Every field narrows the list; `user_id` matches the event's actor or its target."""

    action: str | None = None
    user_id: int | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditEventRepository(SessionRepository):
    async def add(self, data: AuditEventInput) -> AuditEvent:
        event = AuditEvent(
            action=data.action,
            actor_id=data.actor_id,
            target_user_id=data.target_user_id,
            details=data.details,
            ip=data.ip,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list(
        self, filters: AuditEventFilter | None = None, *, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        filters = filters or AuditEventFilter()
        query = select(AuditEvent)
        if filters.action is not None:
            query = query.where(AuditEvent.action == filters.action)
        if filters.user_id is not None:
            query = query.where(
                or_(AuditEvent.actor_id == filters.user_id, AuditEvent.target_user_id == filters.user_id)
            )
        if filters.since is not None:
            query = query.where(AuditEvent.created_at >= filters.since)
        if filters.until is not None:
            query = query.where(AuditEvent.created_at < filters.until)
        # id breaks ties: SQLite's CURRENT_TIMESTAMP only keeps the second.
        query = query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        return list(result.scalars())

    async def count_before(self, instant: datetime) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at < instant)
        )
        return result.scalar_one()

    async def delete_before(self, instant: datetime) -> int:
        """The retention purge's own operation (app/retention/audit.py): the only delete here."""
        # No in-session sync, as in LLMCallRepository.delete_before.
        result = await self._session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < instant).execution_options(synchronize_session=False)
        )
        return result.rowcount
