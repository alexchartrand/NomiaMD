"""Persistence for the ORM models in models.py — one repository class per model, each
owning its own session/query handling."""

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import select

from app.postgresdb.database import async_session
from app.postgresdb.models import ExtractionRecord, Gender, Patient, User, UserRole


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

    async def update_profile(
        self,
        user_id: int,
        *,
        full_name: str,
        physician_type: str | None,
        number_of_patients: int | None,
    ) -> User | None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None
            user.full_name = full_name
            user.physician_type = physician_type
            user.number_of_patients = number_of_patients
            await session.commit()
            await session.refresh(user)
            return user

    async def update_password_hash(self, user_id: int, hashed_password: str) -> None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is not None:
                user.hashed_password = hashed_password
                await session.commit()


class PatientRepository:
    async def list_for_physician(self, physician_id: int) -> Sequence[Patient]:
        async with async_session() as session:
            result = await session.execute(
                select(Patient)
                .where(Patient.physician_id == physician_id, Patient.is_deleted.is_(False))
                .order_by(Patient.full_name)
            )
            return result.scalars().all()

    async def create(
        self,
        *,
        physician_id: int,
        full_name: str,
        ramq_number: str | None,
        date_of_birth: date,
        gender: Gender | None,
        is_registered_with_physician: bool,
        is_vulnerable: bool,
    ) -> Patient:
        async with async_session() as session:
            patient = Patient(
                physician_id=physician_id,
                full_name=full_name,
                ramq_number=ramq_number,
                date_of_birth=date_of_birth,
                gender=gender,
                is_registered_with_physician=is_registered_with_physician,
                is_vulnerable=is_vulnerable,
            )
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
            return patient

    async def get_for_physician(self, patient_id: int, physician_id: int) -> Patient | None:
        async with async_session() as session:
            patient = await session.get(Patient, patient_id)
            if patient is None or patient.physician_id != physician_id or patient.is_deleted:
                return None
            return patient

    async def update_for_physician(
        self,
        patient_id: int,
        physician_id: int,
        *,
        full_name: str,
        ramq_number: str | None,
        date_of_birth: date,
        gender: Gender | None,
        is_registered_with_physician: bool,
        is_vulnerable: bool,
    ) -> Patient | None:
        async with async_session() as session:
            patient = await session.get(Patient, patient_id)
            if patient is None or patient.physician_id != physician_id or patient.is_deleted:
                return None
            patient.full_name = full_name
            patient.ramq_number = ramq_number
            patient.date_of_birth = date_of_birth
            patient.gender = gender
            patient.is_registered_with_physician = is_registered_with_physician
            patient.is_vulnerable = is_vulnerable
            await session.commit()
            await session.refresh(patient)
            return patient

    async def delete_for_physician(self, patient_id: int, physician_id: int) -> bool:
        # Soft delete: billing history must stay readable (name intact) after a patient
        # leaves the roster, and this also guarantees billing_records.patient_id is never
        # dangling — see docs/plans/billing-workflow.md, Part 4.
        async with async_session() as session:
            patient = await session.get(Patient, patient_id)
            if patient is None or patient.physician_id != physician_id or patient.is_deleted:
                return False
            patient.is_deleted = True
            await session.commit()
            return True


@dataclass
class ExtractionRecordInput:
    task: str
    transcript: str
    result: dict
    model: str
    source_system: str | None
    user_id: int


class ExtractionRepository:
    async def create_many(
        self, records: Sequence[ExtractionRecordInput]
    ) -> list[ExtractionRecord]:
        async with async_session() as session:
            created = [
                ExtractionRecord(
                    task=r.task,
                    transcript=r.transcript,
                    result_json=json.dumps(r.result),
                    model=r.model,
                    source_system=r.source_system,
                    user_id=r.user_id,
                )
                for r in records
            ]
            session.add_all(created)
            await session.commit()
            for record in created:
                await session.refresh(record)
            return created
