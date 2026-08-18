"""Login use case: composes password verification, token issuance, and user persistence
so route handlers in app/auth/router.py stay thin (HTTP glue only)."""

from app.auth.security import PasswordHasher, TokenService
from app.postgresdb import User, UserRepository


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self._users = user_repository
        self._hasher = password_hasher
        self._tokens = token_service

    async def login(self, email: str, password: str) -> tuple[str, User] | None:
        """Returns (signed session token, user) on success, None on bad credentials or a
        deactivated account. Deliberately doesn't distinguish "unknown email" from "wrong
        password" in its return value — that distinction belongs in a timing-safe login
        endpoint, not here."""
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            return None
        if not self._hasher.verify(password, user.hashed_password):
            return None
        await self._users.touch_last_login(user.id)
        return self._tokens.issue(user), user

    async def get_user_from_token(self, token: str) -> User | None:
        payload = self._tokens.decode(token)
        if payload is None:
            return None
        user = await self._users.get_by_id(payload.user_id)
        if user is None or not user.is_active:
            return None
        return user
