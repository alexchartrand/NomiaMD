"""Composition root for ClaimService — wires its three repositories together over the
request's single session, so a claim and its code rows commit or roll back together."""

from app.claims.service import ClaimService
from app.postgresdb import ClaimRepository, DbSession, ExtractionRepository, PatientRepository


def get_claim_service(session: DbSession) -> ClaimService:
    return ClaimService(ClaimRepository(session), PatientRepository(session), ExtractionRepository(session))
