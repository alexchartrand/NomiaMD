"""Composition root for the patients router's repositories — both over the request's single
session (see app/postgresdb/dependencies.py), so a handler touching the global Patient and
the physician's roster sees one consistent transaction."""

from app.postgresdb import DbSession, PatientRepository, PhysicianPatientRepository


def get_patient_repository(session: DbSession) -> PatientRepository:
    return PatientRepository(session)


def get_roster_repository(session: DbSession) -> PhysicianPatientRepository:
    return PhysicianPatientRepository(session)
