"""Relational storage (SQLite locally, Postgres in prod — see database.py) for user
accounts and extraction run history. ORM shapes live in models.py, persistence in
repository.py, engine/session wiring in database.py.

Public interface — everything else that needs this imports it from here rather than
reaching into .database/.models/.repository directly."""

from app.postgresdb.database import init_db
from app.postgresdb.models import ExtractionRecord, Gender, Patient, PhysicianType, User, UserRole
from app.postgresdb.repository import (
    ExtractionRecordInput,
    ExtractionRepository,
    PatientRepository,
    UserRepository,
)

__all__ = [
    "init_db",
    "ExtractionRecord",
    "Gender",
    "Patient",
    "PhysicianType",
    "User",
    "UserRole",
    "ExtractionRecordInput",
    "ExtractionRepository",
    "PatientRepository",
    "UserRepository",
]
