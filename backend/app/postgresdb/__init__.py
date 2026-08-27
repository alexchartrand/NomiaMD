"""Relational storage (SQLite locally, Postgres in prod — see database.py) for user
accounts and extraction run history. ORM shapes live in models.py, persistence in
repository.py, engine/session wiring in database.py.

Public interface — everything else that needs this imports it from here rather than
reaching into .database/.models/.repository directly."""

from app.postgresdb.database import init_db
from app.postgresdb.models import (
    Bill,
    BillClaim,
    Claim,
    ClaimCode,
    ExtractionRecord,
    Gender,
    Patient,
    PhysicianProfile,
    PhysicianType,
    RemunerationType,
    User,
    UserRole,
)
from app.postgresdb.repository import (
    BillDetail,
    BillInput,
    ClaimCodeInput,
    ClaimDetail,
    ClaimInput,
    ClaimRepository,
    ClaimWithCodes,
    BillRepository,
    DuplicatePatientRamqNumberError,
    ExtractionRecordInput,
    ExtractionRepository,
    PatientRepository,
    PhysicianProfileRepository,
    UserRepository,
)

__all__ = [
    "init_db",
    "Bill",
    "BillClaim",
    "Claim",
    "ClaimCode",
    "ExtractionRecord",
    "Gender",
    "Patient",
    "PhysicianProfile",
    "PhysicianType",
    "RemunerationType",
    "User",
    "UserRole",
    "BillDetail",
    "BillInput",
    "ClaimCodeInput",
    "ClaimDetail",
    "ClaimInput",
    "ClaimRepository",
    "ClaimWithCodes",
    "BillRepository",
    "DuplicatePatientRamqNumberError",
    "ExtractionRecordInput",
    "ExtractionRepository",
    "PatientRepository",
    "PhysicianProfileRepository",
    "UserRepository",
]
