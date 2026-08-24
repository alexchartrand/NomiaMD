"""Login use case: composes password verification, token issuance, and user persistence
so route handlers in app/auth/router.py stay thin (HTTP glue only)."""

import logging

from app.auth.security import PasswordHasher, TokenService
from app.postgresdb import User, UserRepository

logger = logging.getLogger(__name__)


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

    async def login(self, email: str, password: str, remember_me: bool = False) -> tuple[str, User, int] | None:
        """Returns (signed session token, user, cookie max-age in seconds) on success, None
        on bad credentials or a deactivated account. Deliberately doesn't distinguish
        "unknown email" from "wrong password" in its return value — that distinction
        belongs in a timing-safe login endpoint, not here."""
        user = await self._users.get_by_email(email)
        if user is None:
            logger.warning("Failed login attempt", extra={"email": email, "reason": "unknown_email"})
            return None
        if not user.is_active:
            logger.warning("Failed login attempt", extra={"email": email, "reason": "deactivated"})
            return None
        if not self._hasher.verify(password, user.hashed_password):
            logger.warning("Failed login attempt", extra={"email": email, "reason": "bad_password"})
            return None
        await self._users.touch_last_login(user.id)
        logger.info("Successful login", extra={"email": email})
        token = self._tokens.issue(user, remember_me=remember_me)
        return token, user, self._tokens.expiry_for(remember_me)

    async def get_user_from_token(self, token: str) -> User | None:
        payload = self._tokens.decode(token)
        if payload is None:
            return None
        user = await self._users.get_by_id(payload.user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def update_profile(
        self,
        user: User,
        *,
        full_name: str,
        physician_type: str | None,
        number_of_patients: int | None,
    ) -> User:
        updated = await self._users.update_profile(
            user.id,
            full_name=full_name,
            physician_type=physician_type,
            number_of_patients=number_of_patients,
        )
        if updated is None:
            raise RuntimeError(f"user {user.id} vanished mid-request")
        return updated

    async def change_password(self, user: User, *, current_password: str, new_password: str) -> bool:
        """Returns False on a wrong current password, True once the new one is persisted."""
        if not self._hasher.verify(current_password, user.hashed_password):
            logger.warning(
                "Failed password change attempt",
                extra={"email": user.email, "reason": "bad_current_password"},
            )
            return False
        await self._users.update_password_hash(user.id, self._hasher.hash(new_password))
        logger.info("Password changed", extra={"email": user.email})
        return True
