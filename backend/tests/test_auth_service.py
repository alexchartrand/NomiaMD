"""AuthService against an in-memory user store and a recording hasher: the login timing
guarantees (one verify per attempt, whatever the outcome) and that hashing runs off the
event loop. The HTTP flow is covered end to end in test_auth.py."""

import threading
from types import SimpleNamespace

from app.auth.security import PasswordHasher, TokenService
from app.auth.service import AuthService

PASSWORD = "correct horse battery staple"


class _InMemoryUsers:
    def __init__(self, *users) -> None:
        self._by_email = {user.email: user for user in users}

    async def get_by_email(self, email):
        return self._by_email.get(email)

    async def touch_last_login(self, user_id) -> None:
        pass

    async def update_password_hash(self, user_id, hashed_password) -> None:
        pass


class _RecordingHasher(PasswordHasher):
    """The real Argon2 hasher, noting which method ran and on which thread."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, int]] = []

    def hash(self, password):
        self.calls.append(("hash", threading.get_ident()))
        return super().hash(password)

    def verify(self, password, hashed_password):
        self.calls.append(("verify", threading.get_ident()))
        return super().verify(password, hashed_password)

    def verify_dummy(self, password):
        self.calls.append(("verify_dummy", threading.get_ident()))
        super().verify_dummy(password)


def _user(hasher: PasswordHasher, **overrides):
    defaults = {
        "id": 1,
        "email": "doc@example.test",
        "hashed_password": hasher.hash(PASSWORD),
        "is_active": True,
    }
    return SimpleNamespace(**{**defaults, **overrides})


def _service(hasher: PasswordHasher, *users) -> AuthService:
    return AuthService(
        user_repository=_InMemoryUsers(*users),
        password_hasher=hasher,
        token_service=TokenService("test-secret", 60, 120),
    )


def _call_names(hasher: _RecordingHasher) -> list[str]:
    return [name for name, _ in hasher.calls]


async def test_unknown_email_still_runs_a_password_verify():
    hasher = _RecordingHasher()

    result = await _service(hasher).login("nobody@example.test", PASSWORD)

    assert result is None
    # verify_dummy is itself one Argon2 verify, against the dummy hash.
    assert _call_names(hasher) == ["verify_dummy", "verify"]


async def test_deactivated_account_still_runs_a_password_verify():
    hasher = _RecordingHasher()
    user = _user(hasher, is_active=False)
    hasher.calls.clear()

    result = await _service(hasher, user).login(user.email, PASSWORD)

    assert result is None
    assert _call_names(hasher) == ["verify"]


async def test_wrong_password_runs_one_password_verify():
    hasher = _RecordingHasher()
    user = _user(hasher)
    hasher.calls.clear()

    result = await _service(hasher, user).login(user.email, "not the password")

    assert result is None
    assert _call_names(hasher) == ["verify"]


async def test_login_hashing_runs_off_the_event_loop_thread():
    hasher = _RecordingHasher()
    user = _user(hasher)
    hasher.calls.clear()
    service = _service(hasher, user)

    assert await service.login(user.email, PASSWORD) is not None
    await service.login("nobody@example.test", PASSWORD)

    loop_thread = threading.get_ident()
    assert hasher.calls
    assert all(thread != loop_thread for _, thread in hasher.calls)


async def test_change_password_hashing_runs_off_the_event_loop_thread():
    hasher = _RecordingHasher()
    user = _user(hasher)
    hasher.calls.clear()

    changed = await _service(hasher, user).change_password(
        user, current_password=PASSWORD, new_password="a brand new passphrase"
    )

    assert changed
    loop_thread = threading.get_ident()
    assert _call_names(hasher) == ["verify", "hash"]
    assert all(thread != loop_thread for _, thread in hasher.calls)
