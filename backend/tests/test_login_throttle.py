"""Per-account login throttle (app/auth/throttle.py): the lock policy, the counter against
the real SQLite session with a pinned clock, and the /auth/login behaviour end to end."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.auth.security import PasswordHasher
from app.auth.throttle import LoginLockedError, LoginThrottlePolicy, LoginThrottleService
from app.main import app
from app.postgresdb import UserRepository, UserRole, session_scope

PASSWORD = "correct horse battery staple"
POLICY = LoginThrottlePolicy()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _email() -> str:
    return f"doc-{uuid.uuid4().hex[:8]}@example.test"


def test_policy_allows_attempts_below_the_threshold():
    assert [POLICY.lock_for(n) for n in range(1, POLICY.max_attempts)] == [None] * (POLICY.max_attempts - 1)


def test_policy_locks_for_longer_each_attempt_up_to_the_cap():
    locks = [POLICY.lock_for(n) for n in range(POLICY.max_attempts, POLICY.max_attempts + 4)]

    assert locks == [timedelta(seconds=30), timedelta(seconds=60), timedelta(seconds=120), timedelta(seconds=240)]
    assert POLICY.lock_for(100) == POLICY.max_lock


async def _attempts(throttle: LoginThrottleService, email: str, count: int) -> None:
    for _ in range(count):
        await throttle.reserve(email)


async def test_sixth_attempt_is_refused_after_five_counted():
    clock = _Clock()
    throttle = LoginThrottleService(now=clock)
    email = _email()

    await _attempts(throttle, email, POLICY.max_attempts)

    with pytest.raises(LoginLockedError) as locked:
        await throttle.reserve(email)
    assert locked.value.retry_after == POLICY.base_lock


async def test_lock_expires_and_the_next_lock_is_longer():
    clock = _Clock()
    throttle = LoginThrottleService(now=clock)
    email = _email()
    await _attempts(throttle, email, POLICY.max_attempts)

    clock.advance(POLICY.base_lock + timedelta(seconds=1))
    await throttle.reserve(email)  # allowed again, counts as attempt 6

    with pytest.raises(LoginLockedError) as locked:
        await throttle.reserve(email)
    assert locked.value.retry_after == POLICY.base_lock * 2


async def test_refused_attempts_do_not_extend_the_lock():
    clock = _Clock()
    throttle = LoginThrottleService(now=clock)
    email = _email()
    await _attempts(throttle, email, POLICY.max_attempts)

    for _ in range(3):
        with pytest.raises(LoginLockedError):
            await throttle.reserve(email)
    clock.advance(POLICY.base_lock + timedelta(seconds=1))

    await throttle.reserve(email)


async def test_clear_resets_the_count():
    throttle = LoginThrottleService(now=_Clock())
    email = _email()
    await _attempts(throttle, email, POLICY.max_attempts - 1)

    await throttle.clear(email)

    await _attempts(throttle, email, POLICY.max_attempts - 1)


async def test_old_attempts_are_forgotten():
    clock = _Clock()
    throttle = LoginThrottleService(now=clock)
    email = _email()
    await _attempts(throttle, email, POLICY.max_attempts - 1)

    clock.advance(POLICY.forget_after + timedelta(seconds=1))

    await _attempts(throttle, email, POLICY.max_attempts - 1)


async def test_email_case_and_padding_share_one_counter():
    throttle = LoginThrottleService(now=_Clock())
    email = _email()
    await _attempts(throttle, email, POLICY.max_attempts - 1)

    await throttle.reserve(f"  {email.upper()} ")

    with pytest.raises(LoginLockedError):
        await throttle.reserve(email)


async def test_concurrent_attempts_on_a_new_email_are_all_counted():
    throttle = LoginThrottleService(now=_Clock())
    email = _email()

    results = await asyncio.gather(*(throttle.reserve(email) for _ in range(8)), return_exceptions=True)

    # Five get a turn, the rest find the account locked — none slips through uncounted.
    assert sum(result is None for result in results) == POLICY.max_attempts
    assert all(isinstance(r, LoginLockedError) for r in results if r is not None)


async def _create_user() -> str:
    email = _email()
    async with session_scope() as session:
        await UserRepository(session).create(
            email=email,
            hashed_password=PasswordHasher().hash(PASSWORD),
            full_name="Dr. Doe",
            role=UserRole.PHYSICIAN,
        )
    return email


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


async def test_login_is_locked_after_repeated_wrong_passwords_even_with_the_right_one():
    app.dependency_overrides.pop(get_current_user, None)
    email = await _create_user()
    with TestClient(app) as client:
        statuses = [_login(client, email, "wrong").status_code for _ in range(POLICY.max_attempts)]
        locked = _login(client, email, PASSWORD)

    assert statuses == [401] * POLICY.max_attempts
    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == str(int(POLICY.base_lock.total_seconds()))
    assert "30 secondes" in locked.json()["detail"]


async def test_unknown_email_is_throttled_the_same_way():
    app.dependency_overrides.pop(get_current_user, None)
    email = _email()
    with TestClient(app) as client:
        statuses = [_login(client, email, "wrong").status_code for _ in range(POLICY.max_attempts + 1)]

    assert statuses == [401] * POLICY.max_attempts + [429]


async def test_successful_login_resets_the_count():
    app.dependency_overrides.pop(get_current_user, None)
    email = await _create_user()
    with TestClient(app) as client:
        for _ in range(POLICY.max_attempts - 1):
            _login(client, email, "wrong")
        assert _login(client, email, PASSWORD).status_code == 200
        statuses = [_login(client, email, "wrong").status_code for _ in range(POLICY.max_attempts - 1)]

    assert statuses == [401] * (POLICY.max_attempts - 1)
