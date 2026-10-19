"""Login lockouts as the admin console sees them (app/auth/throttle.py keeps the counters):
which emails have failed attempts, which are locked right now, and lifting a lock."""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.audit import AuditAction, AuditEntry, IAuditLog
from app.auth.throttle import normalize_email
from app.postgresdb import LoginThrottleRepository, User, UserRepository


@dataclass(frozen=True)
class Lockout:
    email: str
    failed_attempts: int
    last_attempt_at: datetime
    locked_until: datetime | None
    # Whether an account has this email: attempts on unknown emails are throttled too (so a
    # lock reveals nothing), and are the likely sign of address guessing.
    known_account: bool

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and _aware(self.locked_until) > datetime.now(timezone.utc)


class LockoutService:
    def __init__(self, throttles: LoginThrottleRepository, users: UserRepository, audit_log: IAuditLog) -> None:
        self._throttles = throttles
        self._users = users
        self._audit = audit_log

    async def list(self) -> list[Lockout]:
        known = {normalize_email(u.email) for u in await self._users.list_all()}
        return [
            Lockout(
                email=t.email,
                failed_attempts=t.failed_attempts,
                last_attempt_at=t.last_attempt_at,
                locked_until=t.locked_until,
                known_account=t.email in known,
            )
            for t in await self._throttles.list_recent()
        ]

    async def unlock(self, actor: User, email: str) -> None:
        key = normalize_email(email)
        await self._throttles.delete(key)
        target = await self._users.get_by_email(email) or await self._users.get_by_email(key)
        await self._audit.record(
            AuditEntry(
                AuditAction.LOGIN_UNLOCKED,
                actor_id=actor.id,
                target_user_id=target.id if target else None,
                # The email is the only handle on an attempt that matched no account.
                details=None if target else {"email": key},
            )
        )


def _aware(instant: datetime) -> datetime:
    # SQLite hands timestamps back naive; they were stored in UTC.
    return instant if instant.tzinfo is not None else instant.replace(tzinfo=timezone.utc)
