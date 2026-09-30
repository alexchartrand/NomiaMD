"""`physician_patients` — a physician's own optional "my patients" list."""

from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Patient, PhysicianPatient
from app.postgresdb.repositories.base import SessionRepository


class DuplicateRosterEntryError(Exception):
    """Raised when a physician tries to add a patient already on their own list."""

    def __init__(self, patient_id: int) -> None:
        self.patient_id = patient_id


class PhysicianPatientRepository(SessionRepository):
    """A physician's own, optional "my patients" list — membership plus a personal note,
    layered on top of the shared global Patient identity. Not a billing gate: see Claim's
    plain FK against Patient and ClaimService.create's use of PatientRepository.get, not
    this class."""

    async def list_roster(self, physician_id: int) -> Sequence[tuple[PhysicianPatient, Patient]]:
        result = await self._session.execute(
            select(PhysicianPatient, Patient)
            .join(Patient, Patient.id == PhysicianPatient.patient_id)
            .where(PhysicianPatient.physician_id == physician_id, Patient.deleted_at.is_(None))
            .order_by(Patient.full_name)
        )
        return result.all()

    async def get_for_physician_and_patient(
        self, physician_id: int, patient_id: int
    ) -> PhysicianPatient | None:
        result = await self._session.execute(
            select(PhysicianPatient).where(
                PhysicianPatient.physician_id == physician_id,
                PhysicianPatient.patient_id == patient_id,
            )
        )
        return result.scalars().first()

    async def add(
        self, physician_id: int, patient_id: int, *, notes: str | None = None
    ) -> PhysicianPatient:
        # Pre-check for the clean error, flush-time IntegrityError on the
        # (physician_id, patient_id) unique constraint for the race — same shape as
        # PatientRepository's duplicate-NAM handling.
        if await self.get_for_physician_and_patient(physician_id, patient_id) is not None:
            raise DuplicateRosterEntryError(patient_id)
        entry = PhysicianPatient(physician_id=physician_id, patient_id=patient_id, notes=notes)
        self._session.add(entry)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRosterEntryError(patient_id) from exc
        await self._session.refresh(entry)
        return entry

    async def update(
        self, physician_id: int, patient_id: int, *, notes: str | None
    ) -> PhysicianPatient | None:
        entry = await self.get_for_physician_and_patient(physician_id, patient_id)
        if entry is None:
            return None
        entry.notes = notes
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def remove(self, physician_id: int, patient_id: int) -> bool:
        result = await self._session.execute(
            delete(PhysicianPatient).where(
                PhysicianPatient.physician_id == physician_id,
                PhysicianPatient.patient_id == patient_id,
            )
        )
        return result.rowcount > 0
