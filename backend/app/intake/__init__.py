"""Where notes come from: every source (paste, extension, scribe, DMÉ) ends up as an
Encounter, which the extraction pipeline then works on. Never imports ramq_codes.

Public interface — everything else that needs this imports it from here."""

# channels and hashing first: importing the service pulls in app.extraction, whose router
# imports Channel and content_hash back from this package while it's still initializing.
from app.intake.channels import Channel
from app.intake.hashing import content_hash
from app.intake.status import EncounterStatus, status_of

from app.intake.connectors import ManualConnector, NoteSplitter, SampleConnector, UnsupportedUploadError
from app.intake.deduplicator import DedupOutcome
from app.intake.models import EncounterMeta, SourceNote
from app.intake.normalizers import NormalizerRegistry, default_normalizers
from app.intake.queue import EncounterExtractor, ExtractionQueue, InlineExtractionQueue
from app.intake.service import (
    EmptyNoteError,
    EncounterNotFoundError,
    IntakeService,
    PatientAlreadyAssignedError,
    PatientNotFoundError,
    ReceiveOutcome,
)
from app.intake.visit_match import SameVisitMatcher

from app.intake.router import router as intake_router
from app.intake.epic_sandbox_router import router as epic_sandbox_router

__all__ = [
    "Channel",
    "DedupOutcome",
    "EmptyNoteError",
    "EncounterExtractor",
    "EncounterNotFoundError",
    "EncounterMeta",
    "EncounterStatus",
    "ExtractionQueue",
    "InlineExtractionQueue",
    "IntakeService",
    "ManualConnector",
    "NormalizerRegistry",
    "NoteSplitter",
    "PatientAlreadyAssignedError",
    "PatientNotFoundError",
    "ReceiveOutcome",
    "SampleConnector",
    "SameVisitMatcher",
    "SourceNote",
    "UnsupportedUploadError",
    "content_hash",
    "default_normalizers",
    "epic_sandbox_router",
    "intake_router",
    "status_of",
]
