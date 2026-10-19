"""Per-account brute-force protection for /auth/login, beside the per-IP limit in
app/rate_limit.py (which an attacker rotating addresses walks around).

Every attempt on an email is counted *before* its password is checked, then wiped by a
successful login. Counting up front is what makes concurrent guesses safe: a burst of
parallel requests each takes its own turn on the row (see LoginThrottleRepository) rather
than all reading "0 failures". From `max_attempts` onward each attempt locks the email for
an exponentially longer time, up to `max_lock`; attempts during a lock are refused without
being counted or checked, so a locked-out physician isn't pushed further out by the
attacker's retries — and the lock is temporary, so it can't be used to deny them their
account for good.

Keyed by the email as typed (lowercased), whether or not an account has it: a lockout that
only appeared for real accounts would reveal which emails exist.

The counter lives in its own short session, never the request's: the route answers a bad
password with a 401, which rolls the request's session back and would erase the failure
just recorded."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from sqlalchemy.exc import IntegrityError

from app.postgresdb import LoginThrottle, LoginThrottleRepository, session_scope

logger = logging.getLogger(__name__)


class LoginLockedError(Exception):
    def __init__(self, retry_after: timedelta) -> None:
        super().__init__(f"login locked for another {retry_after}")
        self.retry_after = retry_after


@dataclass(frozen=True)
class LoginThrottlePolicy:
    max_attempts: int = 5
    base_lock: timedelta = timedelta(seconds=30)
    max_lock: timedelta = timedelta(minutes=15)
    # Attempts this long after the previous one start a fresh count, so a few typos spread
    # over weeks never add up to a lock.
    forget_after: timedelta = timedelta(hours=1)

    def lock_for(self, attempts: int) -> timedelta | None:
        """How long the email is locked once `attempts` have been counted: nothing below
        `max_attempts`, then base_lock doubling per further attempt up to max_lock."""
        if attempts < self.max_attempts:
            return None
        doublings = min(attempts - self.max_attempts, 32)  # the cap bites long before this
        return min(self.base_lock * 2**doublings, self.max_lock)


class ILoginThrottle(Protocol):
    async def reserve(self, email: str) -> None:
        """Counts one attempt on `email`. Raises LoginLockedError instead when it's locked."""
        ...

    async def clear(self, email: str) -> None:
        """Forgets the email's attempts — called after a successful login."""
        ...


class LoginThrottleService(ILoginThrottle):
    def __init__(
        self,
        policy: LoginThrottlePolicy = LoginThrottlePolicy(),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._policy = policy
        self._now = now

    async def reserve(self, email: str) -> None:
        key = _key(email)
        try:
            await self._reserve_once(key)
        except IntegrityError:
            # Two first attempts on a new email raced to insert its row; the other won, so
            # this one now finds the row and takes its turn.
            await self._reserve_once(key)

    async def clear(self, email: str) -> None:
        async with session_scope() as session:
            await LoginThrottleRepository(session).delete(_key(email))

    async def _reserve_once(self, key: str) -> None:
        now = self._now()
        async with session_scope() as session:
            repository = LoginThrottleRepository(session)
            throttle = await repository.get_for_update(key)
            if throttle is None:
                throttle = await repository.add(LoginThrottle(email=key, failed_attempts=0, last_attempt_at=now))

            locked_until = _aware(throttle.locked_until)
            if locked_until is not None and locked_until > now:
                logger.warning("Login attempt refused, account locked", extra={"email": key})
                raise LoginLockedError(locked_until - now)

            if now - _aware(throttle.last_attempt_at) > self._policy.forget_after:
                throttle.failed_attempts = 0
            throttle.failed_attempts += 1
            throttle.last_attempt_at = now
            lock = self._policy.lock_for(throttle.failed_attempts)
            throttle.locked_until = now + lock if lock is not None else None
            if lock is not None:
                logger.warning(
                    "Login locked after repeated attempts",
                    extra={"email": key, "attempts": throttle.failed_attempts, "lock_seconds": lock.total_seconds()},
                )


def _key(email: str) -> str:
    return email.strip().lower()


def _aware(moment: datetime | None) -> datetime | None:
    # SQLite hands back timezone-naive datetimes whatever the column says; everything this
    # module stores is UTC.
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment
