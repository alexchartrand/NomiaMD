"""Epic on FHIR R4: the client, note mapper and reader that both the sandbox demo (step 11b)
and the DSN production connector (step 19) use, plus the sandbox connector itself."""

from app.intake.connectors.epic_fhir.auth import AccessTokenProvider, BackendServicesTokenProvider
from app.intake.connectors.epic_fhir.client import EpicFhirClient, Resource
from app.intake.connectors.epic_fhir.errors import EpicFhirError
from app.intake.connectors.epic_fhir.identifiers import PatientIdentifierStrategy, SandboxIdentifierStrategy
from app.intake.connectors.epic_fhir.mapper import EpicNoteMapper
from app.intake.connectors.epic_fhir.reader import EpicNoteReader
from app.intake.connectors.epic_fhir.sandbox import (
    EPIC_SANDBOX_SOURCE_SYSTEM,
    EpicSandboxConnector,
    EpicSandboxInProductionError,
    ensure_sandbox_allowed,
)
from app.intake.connectors.epic_fhir.sandbox_roster import SandboxPatient, SandboxRoster, demo_nam

__all__ = [
    "EPIC_SANDBOX_SOURCE_SYSTEM",
    "AccessTokenProvider",
    "BackendServicesTokenProvider",
    "EpicFhirClient",
    "EpicFhirError",
    "EpicNoteMapper",
    "EpicNoteReader",
    "EpicSandboxConnector",
    "EpicSandboxInProductionError",
    "PatientIdentifierStrategy",
    "Resource",
    "SandboxIdentifierStrategy",
    "SandboxPatient",
    "SandboxRoster",
    "demo_nam",
    "ensure_sandbox_allowed",
]
