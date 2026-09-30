"""`users` — credentials and the few account fields that live beside them."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.postgresdb.models import User, UserRole
from app.postgresdb.repositories.base import SessionRepository


class UserRepository(SessionRepository):
    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole,
        is_active: bool = True,
        practice_number: str | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=is_active,
            practice_number=practice_number,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

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
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def update_password_hash(self, user_id: int, hashed_password: str) -> None:
        user = await self._session.get(User, user_id)
        if user is not None:
            user.hashed_password = hashed_password
            await self._session.flush()
