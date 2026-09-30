"""Relational storage (SQLite locally, Postgres in prod — see database.py) for user
accounts and extraction run history. ORM shapes live in models.py, persistence in
repositories/, engine wiring in database.py, transaction boundaries in session.py (and
their per-request FastAPI dependency in dependencies.py).

Public interface — everything else that needs this imports it from here rather than
reaching into .database/.models/.repositories directly."""

from app.postgresdb.database import init_db
from app.postgresdb.dependencies import DbSession, get_db_session
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
    PhysicianType,
    RemunerationType,
    User,
    UserRole,
)
from app.postgresdb.repositories import (
    BillInput,
    ClaimCodeInput,
    ClaimDetail,
    ClaimInput,
    ClaimRepository,
    ClaimWithCodes,
    BillRepository,
    DuplicatePatientRamqNumberError,
    DuplicateRosterEntryError,
    ExtractionRecordInput,
    ExtractionRepository,
    PatientRepository,
    PhysicianPatientRepository,
    PhysicianProfileRepository,
    UserRepository,
)
from app.postgresdb.session import session_scope

__all__ = [
    "init_db",
    "session_scope",
    "DbSession",
    "get_db_session",
    "Bill",
    "BillClaim",
    "Claim",
    "ClaimCode",
    "ExtractionRecord",
    "Gender",
    "Patient",
    "PhysicianPatient",
    "PhysicianProfile",
    "PhysicianType",
    "RemunerationType",
    "User",
    "UserRole",
    "BillInput",
    "ClaimCodeInput",
    "ClaimDetail",
    "ClaimInput",
    "ClaimRepository",
    "ClaimWithCodes",
    "BillRepository",
    "DuplicatePatientRamqNumberError",
    "DuplicateRosterEntryError",
    "ExtractionRecordInput",
    "ExtractionRepository",
    "PatientRepository",
    "PhysicianPatientRepository",
    "PhysicianProfileRepository",
    "UserRepository",
]
