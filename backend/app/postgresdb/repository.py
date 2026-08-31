"""Persistence for the ORM models in models.py — one repository class per model, each
owning its own session/query handling."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb.database import async_session
from app.postgresdb.models import (
    Bill,
    BillClaim,
    Claim,
    ClaimCode,
    ExtractionRecord,
    Gender,
    Patient,
    PhysicianPatient,
    PhysicianProfile,
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
        is_active: bool = True,
        practice_number: str | None = None,
    ) -> User:
        async with async_session() as session:
            user = User(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                role=role,
                is_active=is_active,
                practice_number=practice_number,
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

    async def update_editable_fields(
        self, user_id: int, *, full_name: str, practice_number: str | None
    ) -> User | None:
        """The only user-editable fields left on `users` — the rest of the practice facts
        moved to PhysicianProfileRepository. `practice_number` stays here rather than
        joining them: it doesn't change over a career the way panel size does, so it
        doesn't need their append-only history."""
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None
            user.full_name = full_name
            user.practice_number = practice_number
            await session.commit()
            await session.refresh(user)
            return user

    async def update_password_hash(self, user_id: int, hashed_password: str) -> None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is not None:
                user.hashed_password = hashed_password
                await session.commit()


class PhysicianProfileRepository:
    """Append-only history of a physician's practice facts (see PhysicianProfile). Reads
    are "which version applies on date D", never a plain column read."""

    async def get_current(self, user_id: int) -> PhysicianProfile | None:
        return await self.get_effective_on(user_id, date.today())

    async def get_effective_on(self, user_id: int, on: date) -> PhysicianProfile | None:
        """The version in effect on `on` — the latest row that had already taken effect by
        then. Returns None when the physician had no profile yet at that date, which is
        also the answer for a physician who has never filled one in.

        Ties on effective_from break by id so a same-day backfill is deterministic."""
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianProfile)
                .where(
                    PhysicianProfile.user_id == user_id,
                    PhysicianProfile.effective_from <= on,
                )
                .order_by(PhysicianProfile.effective_from.desc(), PhysicianProfile.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_earliest(self, user_id: int) -> PhysicianProfile | None:
        """The physician's very first profile version, regardless of date — a best-effort
        fallback for an encounter dated before any version had taken effect (e.g. a demo
        transcript predating a freshly-onboarded physician's own profile entry), used only
        by app/ramq_codes/context_builder.py's BillingContext resolution. Never used for fee
        calculation (app/bills/service.py keeps calling get_effective_on directly), since a
        bill's fee snapshot must stay strictly historically accurate — this method exists so
        billing_codes has *something* to suggest from instead of leaving the panel-size axis
        unresolved purely because the physician's account is newer than the encounter."""
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianProfile)
                .where(PhysicianProfile.user_id == user_id)
                .order_by(PhysicianProfile.effective_from.asc(), PhysicianProfile.id.asc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def upsert_current(
        self,
        user_id: int,
        *,
        physician_type: str | None,
        number_of_patients: int | None,
        remuneration_type: str | None,
        effective_from: date | None = None,
    ) -> PhysicianProfile:
        """Records today's values as the physician's current version.

        Appends a new row, except when one already takes effect on the same date — that
        one is overwritten in place. Two edits an hour apart are a correction, not two
        versions of reality, and keeping both would grow the table without ever changing
        the answer to `get_effective_on`."""
        effective = effective_from or date.today()
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianProfile).where(
                    PhysicianProfile.user_id == user_id,
                    PhysicianProfile.effective_from == effective,
                )
            )
            profile = result.scalars().first()
            if profile is None:
                profile = PhysicianProfile(user_id=user_id, effective_from=effective)
                session.add(profile)
            profile.physician_type = physician_type
            profile.number_of_patients = number_of_patients
            profile.remuneration_type = remuneration_type
            await session.commit()
            await session.refresh(profile)
            return profile


class DuplicatePatientRamqNumberError(Exception):
    """Raised on a create/update that would leave two active (non-deleted) patients
    sharing a NAM — patients are globally unique by NAM now, not scoped per physician.
    Checked in Python first — same reasoning as ClaimService's billing_extraction_record_id
    pre-check — so the caller gets a clean 409 instead of a raw IntegrityError;
    ix_patients_ramq_number_active (models.py) is the DB-level backstop. The commit itself
    is also wrapped in try/except IntegrityError (see create/update below): the pre-check
    alone leaves a TOCTOU race that's now reachable across *any two physicians* racing to
    create the same real-world patient concurrently, not just one physician double-clicking."""

    def __init__(self, ramq_number: str) -> None:
        self.ramq_number = ramq_number


class DuplicateRosterEntryError(Exception):
    """Raised when a physician tries to add a patient already on their own list."""

    def __init__(self, patient_id: int) -> None:
        self.patient_id = patient_id


_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


class PatientRepository:
    """Global — a Patient is a single identity per NAM, not owned by any physician. See
    PhysicianPatientRepository for a physician's own optional "my patients" list.

    Deliberately has no dependency on app.patients.nam (its richer NAM value object,
    including shape validation) to avoid a circular import — app.patients already depends
    on app.postgresdb, so the reverse dependency isn't available here. `search` below only
    needs simple case/spacing-insensitive comparison, not full NAM validation."""

    async def _raise_if_duplicate_ramq_number(
        self,
        session: AsyncSession,
        *,
        ramq_number: str | None,
        exclude_patient_id: int | None = None,
    ) -> None:
        if ramq_number is None:
            return
        query = select(Patient.id).where(
            Patient.ramq_number == ramq_number,
            Patient.deleted_at.is_(None),
        )
        if exclude_patient_id is not None:
            query = query.where(Patient.id != exclude_patient_id)
        result = await session.execute(query)
        if result.scalars().first() is not None:
            raise DuplicatePatientRamqNumberError(ramq_number)

    async def create(
        self,
        *,
        full_name: str,
        ramq_number: str | None,
        date_of_birth: date,
        gender: Gender | None,
        is_vulnerable: bool,
        family_doctor_name: str | None = None,
        family_doctor_practice_number: str | None = None,
    ) -> Patient:
        async with async_session() as session:
            await self._raise_if_duplicate_ramq_number(session, ramq_number=ramq_number)
            patient = Patient(
                full_name=full_name,
                ramq_number=ramq_number,
                date_of_birth=date_of_birth,
                gender=gender,
                is_vulnerable=is_vulnerable,
                family_doctor_name=family_doctor_name,
                family_doctor_practice_number=family_doctor_practice_number,
            )
            session.add(patient)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicatePatientRamqNumberError(ramq_number) from exc
            await session.refresh(patient)
            return patient

    async def get(self, patient_id: int) -> Patient | None:
        async with async_session() as session:
            patient = await session.get(Patient, patient_id)
            if patient is None or patient.deleted_at is not None:
                return None
            return patient

    async def get_or_create_by_ramq_number(
        self,
        *,
        ramq_number: str,
        full_name: str,
        date_of_birth: date,
        gender: Gender | None,
        is_vulnerable: bool = False,
        family_doctor_name: str | None = None,
        family_doctor_practice_number: str | None = None,
    ) -> Patient:
        """For scripts/seed_db.py: idempotent across re-runs against a not-quite-empty DB,
        and safe if two consultation notes ever shared a NAM."""
        async with async_session() as session:
            result = await session.execute(
                select(Patient).where(Patient.ramq_number == ramq_number, Patient.deleted_at.is_(None))
            )
            existing = result.scalars().first()
            if existing is not None:
                return existing

        return await self.create(
            full_name=full_name,
            ramq_number=ramq_number,
            date_of_birth=date_of_birth,
            gender=gender,
            is_vulnerable=is_vulnerable,
            family_doctor_name=family_doctor_name,
            family_doctor_practice_number=family_doctor_practice_number,
        )

    async def search(self, query: str, *, limit: int = 20) -> list[Patient]:
        """Backs the frontend's patient picker: matches a NAM (case/spacing-insensitive) or
        a substring of the full name. Requires at least 2 characters so a stray keystroke
        doesn't fan out into a live full-table scan."""
        trimmed = query.strip()
        if len(trimmed) < 2:
            return []
        compact_upper = _NOT_ALNUM_RE.sub("", trimmed).upper()
        capped_limit = min(limit, 50)
        async with async_session() as session:
            filters = [func.lower(Patient.full_name).like(f"%{trimmed.lower()}%")]
            if compact_upper:
                filters.append(func.upper(Patient.ramq_number) == compact_upper)
            result = await session.execute(
                select(Patient)
                .where(Patient.deleted_at.is_(None), or_(*filters))
                .order_by(Patient.full_name)
                .limit(capped_limit)
            )
            return list(result.scalars().all())

    async def update(
        self,
        patient_id: int,
        *,
        full_name: str,
        ramq_number: str | None,
        date_of_birth: date,
        gender: Gender | None,
        is_vulnerable: bool,
        family_doctor_name: str | None = None,
        family_doctor_practice_number: str | None = None,
    ) -> Patient | None:
        async with async_session() as session:
            patient = await session.get(Patient, patient_id)
            if patient is None or patient.deleted_at is not None:
                return None
            await self._raise_if_duplicate_ramq_number(
                session, ramq_number=ramq_number, exclude_patient_id=patient_id
            )
            patient.full_name = full_name
            patient.ramq_number = ramq_number
            patient.date_of_birth = date_of_birth
            patient.gender = gender
            patient.is_vulnerable = is_vulnerable
            patient.family_doctor_name = family_doctor_name
            patient.family_doctor_practice_number = family_doctor_practice_number
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicatePatientRamqNumberError(ramq_number) from exc
            await session.refresh(patient)
            return patient

    async def get_many(self, patient_ids: Sequence[int]) -> list[Patient]:
        # Deliberately not filtered on deleted_at — same reasoning as
        # ClaimRepository.list_for_physician's join: a bill's patient details (NAM
        # included) must stay renderable after the patient is gone.
        async with async_session() as session:
            result = await session.execute(select(Patient).where(Patient.id.in_(patient_ids)))
            return list(result.scalars().all())


class PhysicianPatientRepository:
    """A physician's own, optional "my patients" list — membership plus a personal note,
    layered on top of the shared global Patient identity. Not a billing gate: see Claim's
    plain FK against Patient and ClaimService.create's use of PatientRepository.get, not
    this class."""

    async def list_roster(self, physician_id: int) -> Sequence[tuple[PhysicianPatient, Patient]]:
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianPatient, Patient)
                .join(Patient, Patient.id == PhysicianPatient.patient_id)
                .where(PhysicianPatient.physician_id == physician_id, Patient.deleted_at.is_(None))
                .order_by(Patient.full_name)
            )
            return result.all()

    async def get_for_physician_and_patient(
        self, physician_id: int, patient_id: int
    ) -> PhysicianPatient | None:
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianPatient).where(
                    PhysicianPatient.physician_id == physician_id,
                    PhysicianPatient.patient_id == patient_id,
                )
            )
            return result.scalars().first()

    async def add(
        self, physician_id: int, patient_id: int, *, notes: str | None = None
    ) -> PhysicianPatient:
        async with async_session() as session:
            existing = await session.execute(
                select(PhysicianPatient.id).where(
                    PhysicianPatient.physician_id == physician_id,
                    PhysicianPatient.patient_id == patient_id,
                )
            )
            if existing.scalars().first() is not None:
                raise DuplicateRosterEntryError(patient_id)
            entry = PhysicianPatient(physician_id=physician_id, patient_id=patient_id, notes=notes)
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def update(
        self, physician_id: int, patient_id: int, *, notes: str | None
    ) -> PhysicianPatient | None:
        async with async_session() as session:
            result = await session.execute(
                select(PhysicianPatient).where(
                    PhysicianPatient.physician_id == physician_id,
                    PhysicianPatient.patient_id == patient_id,
                )
            )
            entry = result.scalars().first()
            if entry is None:
                return None
            entry.notes = notes
            await session.commit()
            await session.refresh(entry)
            return entry

    async def remove(self, physician_id: int, patient_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                delete(PhysicianPatient).where(
                    PhysicianPatient.physician_id == physician_id,
                    PhysicianPatient.patient_id == patient_id,
                )
            )
            await session.commit()
            return result.rowcount > 0


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
                    result_json=r.result,
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
class ClaimCodeInput:
    code: str
    description: str
    confidence: str
    explanation: str
    fee_amount: Decimal | None
    fee_when_to_use: str | None
    majoration: str | None


@dataclass
class ClaimInput:
    physician_id: int
    patient_id: int
    service_date: date
    status: str
    source_system: str | None
    summary_extraction_record_id: int | None
    billing_extraction_record_id: int | None
    codes: Sequence[ClaimCodeInput]


@dataclass
class ClaimWithCodes:
    record: Claim
    codes: list[ClaimCode]


@dataclass
class ClaimDetail:
    record: Claim
    patient_full_name: str
    codes: list[ClaimCode]


class ClaimRepository:
    """No relationship() — manual second queries, matching the existing house style.
    DB-level cascade is a no-op on SQLite and live on Postgres (see database.py), so nothing
    here may lean on it either way; code rows are always written/deleted explicitly."""

    async def create(self, data: ClaimInput) -> ClaimWithCodes:
        async with async_session() as session:
            record = Claim(
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
                ClaimCode(
                    claim_id=record.id,
                    code=c.code,
                    description=c.description,
                    confidence=c.confidence,
                    explanation=c.explanation,
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
            return ClaimWithCodes(record=record, codes=code_rows)

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
    ) -> list[ClaimDetail]:
        limit = min(limit, 200)
        async with async_session() as session:
            # Joins Patient for the name without filtering deleted_at — a soft-deleted
            # patient's name must still render on an existing claim.
            query = (
                select(Claim, Patient.full_name)
                .join(Patient, Patient.id == Claim.patient_id)
                .where(Claim.physician_id == physician_id)
            )
            if patient_id is not None:
                query = query.where(Claim.patient_id == patient_id)
            if date_from is not None:
                query = query.where(Claim.service_date >= date_from)
            if date_to is not None:
                query = query.where(Claim.service_date <= date_to)
            if status is not None:
                query = query.where(Claim.status == status)
            query = (
                query.order_by(Claim.service_date.desc(), Claim.created_at.desc())
                .limit(limit)
                .offset(offset)
            )

            rows = (await session.execute(query)).all()
            if not rows:
                return []
            names_by_id = {record.id: full_name for record, full_name in rows}

            code_rows = (
                await session.execute(
                    select(ClaimCode).where(
                        ClaimCode.claim_id.in_(names_by_id.keys())
                    )
                )
            ).scalars().all()
            codes_by_record: dict[int, list[ClaimCode]] = {}
            for code_row in code_rows:
                codes_by_record.setdefault(code_row.claim_id, []).append(code_row)

            return [
                ClaimDetail(
                    record=record,
                    patient_full_name=names_by_id[record.id],
                    codes=codes_by_record.get(record.id, []),
                )
                for record, _ in rows
            ]

    async def get_for_physician(self, record_id: int, physician_id: int) -> ClaimDetail | None:
        async with async_session() as session:
            record = await session.get(Claim, record_id)
            if record is None or record.physician_id != physician_id:
                return None
            patient = await session.get(Patient, record.patient_id)
            code_rows = (
                await session.execute(
                    select(ClaimCode).where(ClaimCode.claim_id == record_id)
                )
            ).scalars().all()
            return ClaimDetail(
                record=record,
                patient_full_name=patient.full_name if patient is not None else "",
                codes=list(code_rows),
            )

    async def delete_for_physician(self, record_id: int, physician_id: int) -> bool:
        async with async_session() as session:
            record = await session.get(Claim, record_id)
            if record is None or record.physician_id != physician_id:
                return False
            await session.execute(
                delete(ClaimCode).where(ClaimCode.claim_id == record_id)
            )
            await session.delete(record)
            await session.commit()
            return True

    async def get_by_billing_extraction_record_id(self, billing_extraction_record_id: int) -> Claim | None:
        async with async_session() as session:
            result = await session.execute(
                select(Claim).where(
                    Claim.billing_extraction_record_id == billing_extraction_record_id
                )
            )
            return result.scalar_one_or_none()

    async def count_for_patient_on_date(self, physician_id: int, patient_id: int, service_date: date) -> int:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Claim)
                .where(
                    Claim.physician_id == physician_id,
                    Claim.patient_id == patient_id,
                    Claim.service_date == service_date,
                )
            )
            return result.scalar_one()


@dataclass
class BillInput:
    physician_id: int
    start_date: date
    end_date: date
    claim_ids: Sequence[int]
    total_amount: Decimal | None


@dataclass
class BillDetail:
    bill: Bill
    claims: list[ClaimDetail]


class BillRepository:
    """No relationship() — same house style as ClaimRepository. `create` and
    `delete_for_physician` each do their multi-table write in a single session/commit so a
    bill and its status flip (or release) never land only half-done."""

    async def create(self, data: BillInput) -> Bill | None:
        async with async_session() as session:
            # Re-select the requested claims under physician + status='brouillon'. If the
            # match isn't exact, something changed since the candidate list was loaded (a
            # claim got billed or deleted concurrently) — bail out with nothing written
            # rather than silently billing a subset the physician never confirmed.
            result = await session.execute(
                select(Claim.id).where(
                    Claim.id.in_(data.claim_ids),
                    Claim.physician_id == data.physician_id,
                    Claim.status == "brouillon",
                )
            )
            found_ids = set(result.scalars().all())
            if found_ids != set(data.claim_ids):
                return None

            bill = Bill(
                physician_id=data.physician_id,
                start_date=data.start_date,
                end_date=data.end_date,
                total_amount=data.total_amount,
                record_count=len(data.claim_ids),
            )
            session.add(bill)
            await session.flush()  # populate bill.id for the link rows' FK

            session.add_all(
                BillClaim(bill_id=bill.id, claim_id=claim_id)
                for claim_id in data.claim_ids
            )
            await session.execute(
                update(Claim)
                .where(Claim.id.in_(data.claim_ids))
                .values(status="soumis")
            )
            await session.commit()
            await session.refresh(bill)
            return bill

    async def list_for_physician(self, physician_id: int, *, limit: int = 100, offset: int = 0) -> list[Bill]:
        limit = min(limit, 200)
        async with async_session() as session:
            result = await session.execute(
                select(Bill)
                .where(Bill.physician_id == physician_id)
                .order_by(Bill.generated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_for_physician(self, bill_id: int, physician_id: int) -> Bill | None:
        async with async_session() as session:
            bill = await session.get(Bill, bill_id)
            if bill is None or bill.physician_id != physician_id:
                return None
            return bill

    async def claim_ids_for_bill(self, bill_id: int) -> list[int]:
        async with async_session() as session:
            result = await session.execute(
                select(BillClaim.claim_id).where(BillClaim.bill_id == bill_id)
            )
            return list(result.scalars().all())

    async def delete_for_physician(self, bill_id: int, physician_id: int) -> bool:
        async with async_session() as session:
            bill = await session.get(Bill, bill_id)
            if bill is None or bill.physician_id != physician_id:
                return False

            link_result = await session.execute(
                select(BillClaim.claim_id).where(BillClaim.bill_id == bill_id)
            )
            claim_ids = list(link_result.scalars().all())

            if claim_ids:
                await session.execute(
                    update(Claim)
                    .where(Claim.id.in_(claim_ids))
                    .values(status="brouillon")
                )
            await session.execute(delete(BillClaim).where(BillClaim.bill_id == bill_id))
            await session.delete(bill)
            await session.commit()
            return True
