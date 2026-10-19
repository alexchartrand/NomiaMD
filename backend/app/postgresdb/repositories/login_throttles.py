"""`login_throttles` — failed-login counters per login email."""

from sqlalchemy import delete, select, update

from app.postgresdb.models import LoginThrottle
from app.postgresdb.repositories.base import SessionRepository


class LoginThrottleRepository(SessionRepository):
    async def list_recent(self, *, limit: int = 100) -> list[LoginThrottle]:
        """Emails with failed attempts on record, latest attempt first — what the admin
        console shows as lockouts (locked or on the way to it)."""
        result = await self._session.execute(
            select(LoginThrottle)
            .where(LoginThrottle.failed_attempts > 0)
            .order_by(LoginThrottle.last_attempt_at.desc(), LoginThrottle.email)
            .limit(limit)
        )
        return list(result.scalars())

    async def get_for_update(self, email: str) -> LoginThrottle | None:
        """The row, locked until the session ends, so concurrent attempts on one email
        count one after the other instead of all reading the same counter. Locks with a
        no-op UPDATE rather than SELECT ... FOR UPDATE: that takes the row lock on Postgres
        and, unlike FOR UPDATE (ignored by SQLite, and pysqlite opens no transaction on a
        SELECT), the database write lock on SQLite."""
        await self._session.execute(
            update(LoginThrottle)
            .where(LoginThrottle.email == email)
            .values(failed_attempts=LoginThrottle.failed_attempts)
        )
        result = await self._session.execute(select(LoginThrottle).where(LoginThrottle.email == email))
        return result.scalar_one_or_none()

    async def add(self, throttle: LoginThrottle) -> LoginThrottle:
        """Raises IntegrityError when a concurrent attempt inserted the email first."""
        self._session.add(throttle)
        await self._session.flush()
        return throttle

    async def delete(self, email: str) -> None:
        await self._session.execute(delete(LoginThrottle).where(LoginThrottle.email == email))
