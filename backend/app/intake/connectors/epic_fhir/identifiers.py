"""Which NAM an Epic patient has. Production reads it from Patient.identifier (step 19's
DsnIdentifierStrategy); the sandbox's synthetic patients only carry US identifiers, so a
demo roster maps each one to a fake NAM instead."""

from abc import ABC, abstractmethod

from app.intake.connectors.epic_fhir.client import Resource
from app.intake.connectors.epic_fhir.sandbox_roster import SandboxRoster


class PatientIdentifierStrategy(ABC):
    @abstractmethod
    def nam_for(self, patient: Resource) -> str | None:
        """The patient's NAM, or None — the encounter then waits "à associer"."""


class SandboxIdentifierStrategy(PatientIdentifierStrategy):
    def __init__(self, roster: SandboxRoster) -> None:
        self._roster = roster

    def nam_for(self, patient: Resource) -> str | None:
        entry = self._roster.by_fhir_id(patient.get("id", ""))
        return entry.nam if entry is not None else None
