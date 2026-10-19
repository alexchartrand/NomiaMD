"""Where audit events are written. Two sinks, picked by whether the event must share the
fate of the change it describes:

- SessionAuditLog writes in the caller's transaction — an admin action and its event commit
  or roll back together, so the trail never claims a change that didn't happen.
- DetachedAuditLog writes in its own short session — for login attempts, whose request ends
  in a 401 that rolls the request's session back and would erase the failure being recorded
  (the same reason app/auth/throttle.py keeps its counter out of it)."""

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import AuditAction
from app.postgresdb import AuditEventInput, AuditEventRepository, session_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEntry:
    action: AuditAction
    actor_id: int | None = None
    target_user_id: int | None = None
    details: dict | None = None
    ip: str | None = None

    def to_input(self) -> AuditEventInput:
        return AuditEventInput(
            action=self.action.value,
            actor_id=self.actor_id,
            target_user_id=self.target_user_id,
            details=self.details,
            ip=self.ip,
        )


class IAuditLog(Protocol):
    async def record(self, entry: AuditEntry) -> None: ...


class SessionAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._events = AuditEventRepository(session)

    async def record(self, entry: AuditEntry) -> None:
        await self._events.add(entry.to_input())


class DetachedAuditLog:
    async def record(self, entry: AuditEntry) -> None:
        # Best-effort: a login must not fail because its audit row couldn't be written.
        try:
            async with session_scope() as session:
                await AuditEventRepository(session).add(entry.to_input())
        except Exception:
            logger.exception("Failed to write audit event", extra={"action": entry.action.value})
