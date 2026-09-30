"""Persistence for the ORM models in models.py — one module per aggregate, one repository
class per table.

Every repository is constructed with the AsyncSession it works in and never commits: writes
only `flush()` (to surface constraint violations and populate generated ids), and whoever
opened the session decides the outcome — see session.py. That's what lets a service compose
several repositories into one atomic write."""

from app.postgresdb.repositories.bills import BillInput, BillRepository, ClaimAlreadyBilledError
from app.postgresdb.repositories.claims import (
    ClaimCodeInput,
    ClaimDetail,
    ClaimInput,
    ClaimRepository,
    ClaimWithCodes,
    ExtractionAlreadyClaimedError,
)
from app.postgresdb.repositories.extractions import ExtractionRecordInput, ExtractionRepository
from app.postgresdb.repositories.patients import DuplicatePatientRamqNumberError, PatientRepository
from app.postgresdb.repositories.physician_profiles import PhysicianProfileRepository
from app.postgresdb.repositories.roster import DuplicateRosterEntryError, PhysicianPatientRepository
from app.postgresdb.repositories.users import UserRepository

__all__ = [
    "BillInput",
    "BillRepository",
    "ClaimAlreadyBilledError",
    "ClaimCodeInput",
    "ClaimDetail",
    "ClaimInput",
    "ClaimRepository",
    "ClaimWithCodes",
    "ExtractionAlreadyClaimedError",
    "DuplicatePatientRamqNumberError",
    "DuplicateRosterEntryError",
    "ExtractionRecordInput",
    "ExtractionRepository",
    "PatientRepository",
    "PhysicianPatientRepository",
    "PhysicianProfileRepository",
    "UserRepository",
]
