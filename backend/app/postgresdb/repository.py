"""Persistence for the ORM models in models.py — one repository class per model, each
owning its own session/query handling."""

import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.postgresdb.database import async_session
from app.postgresdb.models import ExtractionRecord, User, UserRole


class UserRepository:
    async def get_by_email(self, email: str) -> User | None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        async with async_session() as session:
            return await session.get(User, user_id)

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole,
        physician_type: str | None = None,
        number_of_patients: int | None = None,
        is_active: bool = True,
    ) -> User:
        async with async_session() as session:
            user = User(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                role=role,
                physician_type=physician_type,
                number_of_patients=number_of_patients,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def touch_last_login(self, user_id: int) -> None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is not None:
                user.last_login_at = datetime.now(timezone.utc)
                await session.commit()


class ExtractionRepository:
    async def create(
        self,
        *,
        task: str,
        transcript: str,
        result: dict,
        model: str,
        source_system: str | None,
        user_id: int,
    ) -> ExtractionRecord:
        async with async_session() as session:
            record = ExtractionRecord(
                task=task,
                transcript=transcript,
                result_json=json.dumps(result),
                model=model,
                source_system=source_system,
                user_id=user_id,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record
