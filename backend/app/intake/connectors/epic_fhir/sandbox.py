"""The demo connector: signed notes of Epic's synthetic sandbox patients (fhir.epic.com),
pulled through the same client/mapper/reader the production connector (step 19) will use.
Off by default, and refused in production so sandbox data never mixes with real data."""

from collections.abc import Callable
from datetime import date

from app.intake.connectors.base import PullConnector
from app.intake.connectors.epic_fhir.client import Resource
from app.intake.connectors.epic_fhir.reader import EpicNoteReader
from app.intake.connectors.epic_fhir.sandbox_roster import SandboxPatient, SandboxRoster
from app.intake.models import SourceNote
from app.postgresdb import User

EPIC_SANDBOX_SOURCE_SYSTEM = "epic_sandbox"


class EpicSandboxInProductionError(RuntimeError):
    """EPIC_SANDBOX_ENABLED is on in an environment marked production."""


class EpicSandboxConnector(PullConnector):
    def __init__(self, reader: EpicNoteReader, roster: SandboxRoster) -> None:
        self._reader = reader
        self._roster = roster

    async def fetch_signed_notes(self, user: User, since: date | None = None) -> list[SourceNote]:
        # A system-level token reads every sandbox patient: `user` only matters once
        # per-user tokens arrive (step 19).
        notes = []
        for patient in self._roster.patients():
            notes += await self._reader.signed_notes(patient.fhir_id, since, include=_listed_in(patient))
        return notes


def _listed_in(patient: SandboxPatient) -> Callable[[Resource], bool]:
    """Only the roster's notes: the shared sandbox also holds other apps' test notes."""

    def include(document: Resource) -> bool:
        return document.get("id") in patient.note_ids

    return include


def ensure_sandbox_allowed(enabled: bool, environment: str) -> None:
    if enabled and environment == "production":
        raise EpicSandboxInProductionError(
            "EPIC_SANDBOX_ENABLED is on while APP_ENV=production: sandbox notes must never "
            "reach a production database. Turn the flag off."
        )
