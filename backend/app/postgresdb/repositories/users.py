"""`users` — credentials and the few account fields that live beside them."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Claim, Encounter, User, UserRole
from app.postgresdb.repositories.base import SessionRepository


class DuplicatePracticeNumberError(Exception):
    """Another account already holds this practice number — users.practice_number is
    unique, since registration is derived by matching it (app/patients/registration.py).
    The session can only be rolled back afterwards, which its owner does as this propagates
    (see session.py)."""


class DuplicateEmailError(Exception):
    """Another account already has this email (users.email is unique)."""


def _violates_unique(exc: IntegrityError, column: str) -> bool:
    message = str(exc.orig).lower()
    return "unique" in message and column in message


@dataclass(frozen=True)
class AccountActivity:
    encounters: int = 0
    claims: int = 0


class UserRepository(SessionRepository):
    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def list_all(self) -> list[User]:
        result = await self._session.execute(select(User).order_by(User.full_name, User.id))
        return list(result.scalars())

    async def activity_by_user(self) -> dict[int, AccountActivity]:
        """Encounters and live (non-voided) claims per account — two grouped counts, not one
        query per user. Accounts with neither are absent; read them as AccountActivity()."""
        encounters = await self._session.execute(
            select(Encounter.user_id, func.count()).group_by(Encounter.user_id)
        )
        claims = await self._session.execute(
            select(Claim.physician_id, func.count()).where(Claim.voided_at.is_(None)).group_by(Claim.physician_id)
        )
        encounter_counts = dict(encounters.tuples().all())
        claim_counts = dict(claims.tuples().all())
        return {
            user_id: AccountActivity(encounters=encounter_counts.get(user_id, 0), claims=claim_counts.get(user_id, 0))
            for user_id in encounter_counts.keys() | claim_counts.keys()
        }

    async def count_active_admins(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole,
        is_active: bool = True,
        practice_number: str | None = None,
        must_change_password: bool = False,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=is_active,
            practice_number=practice_number,
            must_change_password=must_change_password,
        )
        self._session.add(user)
        await self._flush_or_raise_duplicate()
        return user

    async def _flush_or_raise_duplicate(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _violates_unique(exc, "practice_number"):
                raise DuplicatePracticeNumberError() from exc
            if _violates_unique(exc, "email"):
                raise DuplicateEmailError() from exc
            raise

    async def touch_last_login(self, user_id: int) -> None:
        user = await self._session.get(User, user_id)
        if user is not None:
            user.last_login_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def update_editable_fields(
        self, user_id: int, *, full_name: str, practice_number: str | None
    ) -> User | None:
        """The only user-editable fields left on `users` — the rest of the practice facts
        moved to PhysicianProfileRepository. `practice_number` stays here rather than
        joining them: it doesn't change over a career the way panel size does, so it
        doesn't need their append-only history."""
        user = await self._session.get(User, user_id)
        if user is None:
            return None
        user.full_name = full_name
        user.practice_number = practice_number
        await self._flush_or_raise_duplicate()
        return user

    async def update_password_hash(self, user_id: int, hashed_password: str) -> None:
        user = await self._session.get(User, user_id)
        if user is not None:
            user.hashed_password = hashed_password
            await self._session.flush()

    async def set_password(self, user_id: int, hashed_password: str, *, must_change: bool) -> None:
        """An admin-issued password: replaces the hash and ends every open session, since
        whoever held the old password must not stay logged in."""
        user = await self._require(user_id)
        user.hashed_password = hashed_password
        user.must_change_password = must_change
        user.session_version += 1
        await self._session.flush()

    async def set_must_change_password(self, user_id: int, value: bool) -> None:
        user = await self._require(user_id)
        user.must_change_password = value
        await self._session.flush()

    async def set_active(self, user_id: int, active: bool) -> User:
        """Deactivation also ends every open session — not strictly needed, since the active
        check runs on every request, but it keeps reactivation from reviving old cookies."""
        user = await self._require(user_id)
        user.is_active = active
        user.deactivated_at = None if active else datetime.now(timezone.utc)
        if not active:
            user.session_version += 1
        await self._session.flush()
        return user

    async def set_role(self, user_id: int, role: UserRole) -> User:
        user = await self._require(user_id)
        if user.role != role:
            user.role = role
            user.session_version += 1
            await self._session.flush()
        return user

    async def bump_session_version(self, user_id: int) -> None:
        user = await self._require(user_id)
        user.session_version += 1
        await self._session.flush()

    async def _require(self, user_id: int) -> User:
        user = await self._session.get(User, user_id)
        if user is None:
            raise LookupError(f"user {user_id} not found")
        return user
