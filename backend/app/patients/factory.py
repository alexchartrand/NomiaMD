"""Composition root for the patients router's repositories and search, all over the
request's single session (see app/postgresdb/dependencies.py), so a handler touching the
global Patient and the physician's roster sees one consistent transaction."""

from fastapi import Depends

from app.patients.search import PatientSearch
from app.postgresdb import DbSession, PatientRepository, PhysicianPatientRepository


def get_patient_repository(session: DbSession) -> PatientRepository:
    return PatientRepository(session)


def get_roster_repository(session: DbSession) -> PhysicianPatientRepository:
    return PhysicianPatientRepository(session)


def get_patient_search(patients: PatientRepository = Depends(get_patient_repository)) -> PatientSearch:
    return PatientSearch(patients)
