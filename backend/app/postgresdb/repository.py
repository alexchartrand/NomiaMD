"""Persistence for the ORM models in models.py — one repository class per model, each
owning its own session/query handling."""

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import delete, func, select

from app.postgresdb.database import async_session
from app.postgresdb.models import (
    BillingRecord,
    BillingRecordCode,
    ExtractionRecord,
    Gender,
    Patient,
    User,
    UserRole,
)


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

    async def get_for_user(self, record_id: int, user_id: int) -> ExtractionRecord | None:
        async with async_session() as session:
            record = await session.get(ExtractionRecord, record_id)
            if record is None or record.user_id != user_id:
                return None
            return record


@dataclass
class BillingRecordCodeInput:
    code: str
    description: str
    confidence: float
    supporting_quote: str
    fee_amount: float | None
    fee_when_to_use: str | None
    majoration: str | None


@dataclass
class BillingRecordInput:
    physician_id: int
    patient_id: int
    service_date: date
    status: str
    source_system: str | None
    summary_extraction_record_id: int | None
    billing_extraction_record_id: int | None
    codes: Sequence[BillingRecordCodeInput]


@dataclass
class BillingRecordWithCodes:
    record: BillingRecord
    codes: list[BillingRecordCode]


@dataclass
class BillingRecordDetail:
    record: BillingRecord
    patient_full_name: str
    codes: list[BillingRecordCode]


class BillingRecordRepository:
    """No relationship() — manual second queries, matching the existing house style.
    DB-level cascade is a no-op on SQLite and live on Postgres (see database.py), so nothing
    here may lean on it either way; code rows are always written/deleted explicitly."""

    async def create(self, data: BillingRecordInput) -> BillingRecordWithCodes:
        async with async_session() as session:
            record = BillingRecord(
                physician_id=data.physician_id,
                patient_id=data.patient_id,
                service_date=data.service_date,
                status=data.status,
                source_system=data.source_system,
                summary_extraction_record_id=data.summary_extraction_record_id,
                billing_extraction_record_id=data.billing_extraction_record_id,
            )
            session.add(record)
            await session.flush()  # populate record.id for the code rows' FK
            code_rows = [
                BillingRecordCode(
                    billing_record_id=record.id,
                    code=c.code,
                    description=c.description,
                    confidence=c.confidence,
                    supporting_quote=c.supporting_quote,
                    fee_amount=c.fee_amount,
                    fee_when_to_use=c.fee_when_to_use,
                    majoration=c.majoration,
                )
                for c in data.codes
            ]
            session.add_all(code_rows)
            await session.commit()
            await session.refresh(record)
            for row in code_rows:
                await session.refresh(row)
            return BillingRecordWithCodes(record=record, codes=code_rows)

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        patient_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BillingRecordDetail]:
        limit = min(limit, 200)
        async with async_session() as session:
            # Joins Patient for the name without filtering is_deleted — a soft-deleted
            # patient's name must still render on an existing billing record.
            query = (
                select(BillingRecord, Patient.full_name)
                .join(Patient, Patient.id == BillingRecord.patient_id)
                .where(BillingRecord.physician_id == physician_id)
            )
            if patient_id is not None:
                query = query.where(BillingRecord.patient_id == patient_id)
            if date_from is not None:
                query = query.where(BillingRecord.service_date >= date_from)
            if date_to is not None:
                query = query.where(BillingRecord.service_date <= date_to)
            if status is not None:
                query = query.where(BillingRecord.status == status)
            query = (
                query.order_by(BillingRecord.service_date.desc(), BillingRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )

            rows = (await session.execute(query)).all()
            if not rows:
                return []
            names_by_id = {record.id: full_name for record, full_name in rows}

            code_rows = (
                await session.execute(
                    select(BillingRecordCode).where(
                        BillingRecordCode.billing_record_id.in_(names_by_id.keys())
                    )
                )
            ).scalars().all()
            codes_by_record: dict[int, list[BillingRecordCode]] = {}
            for code_row in code_rows:
                codes_by_record.setdefault(code_row.billing_record_id, []).append(code_row)

            return [
                BillingRecordDetail(
                    record=record,
                    patient_full_name=names_by_id[record.id],
                    codes=codes_by_record.get(record.id, []),
                )
                for record, _ in rows
            ]

    async def get_for_physician(self, record_id: int, physician_id: int) -> BillingRecordDetail | None:
        async with async_session() as session:
            record = await session.get(BillingRecord, record_id)
            if record is None or record.physician_id != physician_id:
                return None
            patient = await session.get(Patient, record.patient_id)
            code_rows = (
                await session.execute(
                    select(BillingRecordCode).where(BillingRecordCode.billing_record_id == record_id)
                )
            ).scalars().all()
            return BillingRecordDetail(
                record=record,
                patient_full_name=patient.full_name if patient is not None else "",
                codes=list(code_rows),
            )

    async def update_status_for_physician(
        self, record_id: int, physician_id: int, *, status: str
    ) -> BillingRecord | None:
        async with async_session() as session:
            record = await session.get(BillingRecord, record_id)
            if record is None or record.physician_id != physician_id:
                return None
            record.status = status
            await session.commit()
            await session.refresh(record)
            return record

    async def delete_for_physician(self, record_id: int, physician_id: int) -> bool:
        async with async_session() as session:
            record = await session.get(BillingRecord, record_id)
            if record is None or record.physician_id != physician_id:
                return False
            await session.execute(
                delete(BillingRecordCode).where(BillingRecordCode.billing_record_id == record_id)
            )
            await session.delete(record)
            await session.commit()
            return True

    async def get_by_billing_extraction_record_id(self, billing_extraction_record_id: int) -> BillingRecord | None:
        async with async_session() as session:
            result = await session.execute(
                select(BillingRecord).where(
                    BillingRecord.billing_extraction_record_id == billing_extraction_record_id
                )
            )
            return result.scalar_one_or_none()

    async def count_for_patient_on_date(self, physician_id: int, patient_id: int, service_date: date) -> int:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(BillingRecord)
                .where(
                    BillingRecord.physician_id == physician_id,
                    BillingRecord.patient_id == patient_id,
                    BillingRecord.service_date == service_date,
                )
            )
            return result.scalar_one()
