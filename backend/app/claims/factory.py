"""Composition root for ClaimService — wires its three repositories together."""

from app.claims.service import ClaimService
from app.postgresdb import ClaimRepository, ExtractionRepository, PatientRepository


def get_claim_service() -> ClaimService:
    return ClaimService(ClaimRepository(), PatientRepository(), ExtractionRepository())
