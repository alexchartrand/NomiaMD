"""Persistence for the ORM models in models.py — one module per aggregate, one repository
class per table.

Every repository is constructed with the AsyncSession it works in and never commits: writes
only `flush()` (to surface constraint violations and populate generated ids), and whoever
opened the session decides the outcome — see session.py. That's what lets a service compose
several repositories into one atomic write."""

from app.postgresdb.repositories.bills import BillInput, BillRepository
from app.postgresdb.repositories.claims import (
    ClaimAlreadyBilledError,
    ClaimCodeInput,
    ClaimContextInput,
    ClaimDetail,
    ClaimInput,
    ClaimRepository,
    ClaimWithCodes,
    ExtractionAlreadyClaimedError,
)
from app.postgresdb.repositories.contact_requests import ContactRequestInput, ContactRequestRepository
from app.postgresdb.repositories.encounters import (
    DuplicateEncounterError,
    EncounterActivity,
    ReceivedWindow,
    EncounterPeriod,
    EncounterInput,
    EncounterRepository,
)
from app.postgresdb.repositories.extractions import (
    ExtractionRepository,
    ExtractionRunInput,
    ExtractionStageInput,
)
from app.postgresdb.repositories.patients import DuplicatePatientRamqNumberError, PatientRepository
from app.postgresdb.repositories.physician_profiles import PhysicianProfileRepository
from app.postgresdb.repositories.roster import DuplicateRosterEntryError, PhysicianPatientRepository
from app.postgresdb.repositories.users import DuplicatePracticeNumberError, UserRepository

__all__ = [
    "BillInput",
    "BillRepository",
    "ClaimAlreadyBilledError",
    "ClaimCodeInput",
    "ClaimContextInput",
    "ClaimDetail",
    "ClaimInput",
    "ClaimRepository",
    "ClaimWithCodes",
    "ExtractionAlreadyClaimedError",
    "ContactRequestInput",
    "ContactRequestRepository",
    "DuplicateEncounterError",
    "DuplicatePatientRamqNumberError",
    "DuplicatePracticeNumberError",
    "DuplicateRosterEntryError",
    "EncounterActivity",
    "ReceivedWindow",
    "EncounterPeriod",
    "EncounterInput",
    "EncounterRepository",
    "ExtractionRepository",
    "ExtractionRunInput",
    "ExtractionStageInput",
    "PatientRepository",
    "PhysicianPatientRepository",
    "PhysicianProfileRepository",
    "UserRepository",
]
