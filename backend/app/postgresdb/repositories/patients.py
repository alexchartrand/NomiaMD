"""`patients` — the global, NAM-unique patient identity."""

import re
from datetime import date
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Gender, Patient
from app.postgresdb.repositories.base import SessionRepository


class DuplicatePatientRamqNumberError(Exception):
    """Raised on a create/update that would leave two active (non-deleted) patients
    sharing a NAM — patients are globally unique by NAM now, not scoped per physician.
    Checked in Python first — same reasoning as ClaimService's billing_extraction_record_id
    pre-check — so the caller gets a clean 409 instead of a raw IntegrityError;
    ix_patients_ramq_number_active (models.py) is the DB-level backstop. The flush itself is
    also wrapped in try/except IntegrityError (see create/update below): the pre-check alone
    leaves a TOCTOU race that's reachable across *any two physicians* racing to create the
    same real-world patient concurrently, not just one physician double-clicking. After that
    IntegrityError the session can only be rolled back — which its owner does as this
    exception propagates (see session.py)."""

    def __init__(self, ramq_number: str) -> None:
        self.ramq_number = ramq_number


_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


class PatientRepository(SessionRepository):
    """Global — a Patient is a single identity per NAM, not owned by any physician. See
    PhysicianPatientRepository for a physician's own optional "my patients" list.

    Deliberately has no dependency on app.patients.nam (its richer NAM value object,
    including shape validation) to avoid a circular import — app.patients already depends
    on app.postgresdb, so the reverse dependency isn't available here. `search` below only
    needs simple case/spacing-insensitive comparison, not full NAM validation."""

    async def _raise_if_duplicate_ramq_number(
        self,
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
        result = await self._session.execute(query)
        if result.scalars().first() is not None:
            raise DuplicatePatientRamqNumberError(ramq_number)

    async def _flush_or_raise_duplicate(self, ramq_number: str | None) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicatePatientRamqNumberError(ramq_number) from exc

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
        await self._raise_if_duplicate_ramq_number(ramq_number=ramq_number)
        patient = Patient(
            full_name=full_name,
            ramq_number=ramq_number,
            date_of_birth=date_of_birth,
            gender=gender,
            is_vulnerable=is_vulnerable,
            family_doctor_name=family_doctor_name,
            family_doctor_practice_number=family_doctor_practice_number,
        )
        self._session.add(patient)
        await self._flush_or_raise_duplicate(ramq_number)
        await self._session.refresh(patient)
        return patient

    async def get(self, patient_id: int) -> Patient | None:
        patient = await self._session.get(Patient, patient_id)
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
        result = await self._session.execute(
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
        filters = [func.lower(Patient.full_name).like(f"%{trimmed.lower()}%")]
        if compact_upper:
            filters.append(func.upper(Patient.ramq_number) == compact_upper)
        result = await self._session.execute(
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
        patient = await self._session.get(Patient, patient_id)
        if patient is None or patient.deleted_at is not None:
            return None
        await self._raise_if_duplicate_ramq_number(ramq_number=ramq_number, exclude_patient_id=patient_id)
        patient.full_name = full_name
        patient.ramq_number = ramq_number
        patient.date_of_birth = date_of_birth
        patient.gender = gender
        patient.is_vulnerable = is_vulnerable
        patient.family_doctor_name = family_doctor_name
        patient.family_doctor_practice_number = family_doctor_practice_number
        await self._flush_or_raise_duplicate(ramq_number)
        await self._session.refresh(patient)
        return patient

    async def get_many(self, patient_ids: Sequence[int]) -> list[Patient]:
        # Deliberately not filtered on deleted_at — same reasoning as
        # ClaimRepository.list_for_physician's join: a bill's patient details (NAM
        # included) must stay renderable after the patient is gone.
        result = await self._session.execute(select(Patient).where(Patient.id.in_(patient_ids)))
        return list(result.scalars().all())
