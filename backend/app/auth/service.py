"""Login use case: composes password verification, token issuance, and user persistence
so route handlers in app/auth/router.py stay thin (HTTP glue only)."""

import asyncio
import logging

from app.audit import AuditAction, AuditEntry, IAuditLog
from app.auth.security import PasswordHasher, TokenService
from app.auth.throttle import ILoginThrottle
from app.postgresdb import User, UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        login_throttle: ILoginThrottle,
        audit_log: IAuditLog,
        failure_audit_log: IAuditLog,
    ) -> None:
        self._users = user_repository
        self._hasher = password_hasher
        self._tokens = token_service
        self._throttle = login_throttle
        # Successes write in the request's session, beside the writes they follow
        # (last_login_at, the new hash). Failures write detached from it (app/audit/log.py):
        # their 401 rolls that session back.
        self._audit = audit_log
        self._failure_audit = failure_audit_log

    async def login(
        self, email: str, password: str, remember_me: bool = False, *, client_ip: str | None = None
    ) -> tuple[str, User, int] | None:
        """Returns (signed session token, user, cookie max-age in seconds) on success, None
        on bad credentials or a deactivated account. Every attempt runs exactly one Argon2
        verify — against a dummy hash for an unknown email, before the active check for a
        known one — so response time doesn't reveal which emails have an account.

        Raises LoginLockedError, before any verify, while the email is locked out after
        repeated attempts (app/auth/throttle.py).

        Attempts on a real account are written to the audit trail; unknown emails aren't,
        so guessing addresses can't grow it."""
        await self._throttle.reserve(email)
        user = await self._users.get_by_email(email)
        if user is None:
            await asyncio.to_thread(self._hasher.verify_dummy, password)
            logger.warning("Failed login attempt", extra={"email": email, "reason": "unknown_email"})
            return None
        password_matches = await self._verify(password, user.hashed_password)
        if not user.is_active:
            logger.warning("Failed login attempt", extra={"email": email, "reason": "deactivated"})
            await self._record_login_failure(user, "deactivated", client_ip)
            return None
        if not password_matches:
            logger.warning("Failed login attempt", extra={"email": email, "reason": "bad_password"})
            await self._record_login_failure(user, "bad_password", client_ip)
            return None
        await self._throttle.clear(email)
        await self._users.touch_last_login(user.id)
        logger.info("Successful login", extra={"email": email})
        await self._audit.record(
            AuditEntry(AuditAction.LOGIN_SUCCEEDED, actor_id=user.id, target_user_id=user.id, ip=client_ip)
        )
        token = self._tokens.issue(user, remember_me=remember_me)
        return token, user, self._tokens.expiry_for(remember_me)

    async def get_user_from_token(self, token: str) -> User | None:
        payload = self._tokens.decode(token)
        if payload is None:
            return None
        user = await self._users.get_by_id(payload.user_id)
        if user is None or not user.is_active:
            return None
        if payload.session_version != user.session_version:
            # Revoked: the account's sessions were ended (deactivation, admin reset, role
            # change, "log out everywhere") after this token was issued.
            return None
        return user

    async def change_password(self, user: User, *, current_password: str, new_password: str) -> bool:
        """Returns False on a wrong current password, True once the new one is persisted."""
        if not await self._verify(current_password, user.hashed_password):
            logger.warning(
                "Failed password change attempt",
                extra={"email": user.email, "reason": "bad_current_password"},
            )
            return False
        new_hash = await asyncio.to_thread(self._hasher.hash, new_password)
        await self._users.update_password_hash(user.id, new_hash)
        if user.must_change_password:
            await self._users.set_must_change_password(user.id, False)
        logger.info("Password changed", extra={"email": user.email})
        await self._audit.record(AuditEntry(AuditAction.PASSWORD_CHANGED, actor_id=user.id, target_user_id=user.id))
        return True

    async def _record_login_failure(self, user: User, reason: str, client_ip: str | None) -> None:
        await self._failure_audit.record(
            AuditEntry(AuditAction.LOGIN_FAILED, target_user_id=user.id, details={"reason": reason}, ip=client_ip)
        )

    async def _verify(self, password: str, hashed_password: str) -> bool:
        # Argon2 is CPU-slow by design; run it off the event loop so a login doesn't stall
        # other physicians' in-flight requests.
        return await asyncio.to_thread(self._hasher.verify, password, hashed_password)
