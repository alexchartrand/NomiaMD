"""Password hashing and session-token issuance/verification. Pure business logic — no
FastAPI, no database — so it can be unit-tested in isolation from the request/response
cycle and from persistence."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import VerifyMismatchError

from app.postgresdb import User


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = _Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, hashed_password: str) -> bool:
        try:
            return self._hasher.verify(hashed_password, password)
        except VerifyMismatchError:
            return False


@dataclass
class TokenPayload:
    user_id: int


class TokenService:
    """Issues and verifies the JWT stored in the session cookie. HS256 is enough here —
    one backend process both signs and verifies, so there's no need for asymmetric keys."""

    ALGORITHM = "HS256"

    def __init__(self, secret_key: str, expiry_seconds: int) -> None:
        self._secret_key = secret_key
        self._expiry_seconds = expiry_seconds

    def issue(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(seconds=self._expiry_seconds),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self.ALGORITHM)

    def decode(self, token: str) -> TokenPayload | None:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self.ALGORITHM])
        except jwt.InvalidTokenError:
            return None
        return TokenPayload(user_id=int(payload["sub"]))
