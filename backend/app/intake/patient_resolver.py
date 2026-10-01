"""Which patient a note is about — from the source's structured NAM only. Never reads the
note text and never asks the LLM: identity is an administrative fact (CLAUDE.md)."""

from app.patients.nam import normalize
from app.postgresdb import PatientRepository


class PatientResolver:
    def __init__(self, patients: PatientRepository) -> None:
        self._patients = patients

    async def resolve(self, nam: str | None) -> int | None:
        """The active patient with this NAM, or None — no NAM, a malformed one, or one
        nobody registered. None leaves the encounter "à associer" for the physician."""
        canonical = normalize(nam)
        if canonical is None:
            return None
        patient = await self._patients.get_by_ramq_number(canonical)
        return patient.id if patient is not None else None
