"""Password hashing and session-token issuance/verification. Pure business logic — no
FastAPI, no database — so it can be unit-tested in isolation from the request/response
cycle and from persistence."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import cached_property

import jwt
from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import VerifyMismatchError

from app.postgresdb import User


class PasswordHasher:
    """Argon2 hashing. Every call is deliberately CPU-slow and synchronous — async callers
    run it in a worker thread so it doesn't stall the event loop."""

    def __init__(self) -> None:
        self._hasher = _Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, hashed_password: str) -> bool:
        try:
            return self._hasher.verify(hashed_password, password)
        except VerifyMismatchError:
            return False

    def verify_dummy(self, password: str) -> None:
        """Spends the time of a real verify against a hash no password matches, so a login
        for an unknown email takes as long as one for a known email."""
        self.verify(password, self._dummy_hash)

    @cached_property
    def _dummy_hash(self) -> str:
        # Built on first use: the hash costs as much as a verify, and most hashers
        # (tests, scripts) never need it.
        return self._hasher.hash(secrets.token_urlsafe(32))


@dataclass
class TokenPayload:
    user_id: int


class TokenService:
    """Issues and verifies the JWT stored in the session cookie. HS256 is enough here —
    one backend process both signs and verifies, so there's no need for asymmetric keys."""

    ALGORITHM = "HS256"

    def __init__(self, secret_key: str, expiry_seconds: int, remember_me_expiry_seconds: int) -> None:
        self._secret_key = secret_key
        self._expiry_seconds = expiry_seconds
        self._remember_me_expiry_seconds = remember_me_expiry_seconds

    def expiry_for(self, remember_me: bool) -> int:
        return self._remember_me_expiry_seconds if remember_me else self._expiry_seconds

    def issue(self, user: User, remember_me: bool = False) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(seconds=self.expiry_for(remember_me)),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self.ALGORITHM)

    def decode(self, token: str) -> TokenPayload | None:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self.ALGORITHM])
        except jwt.InvalidTokenError:
            return None
        return TokenPayload(user_id=int(payload["sub"]))
