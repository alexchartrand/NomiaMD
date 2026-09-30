"""Composition root for ClaimService — wires its three repositories (and the duplicate
guard built on the claims one) together over the request's single session, so a claim and
its code rows commit or roll back together."""

from app.claims.duplicates import ClaimDuplicateGuard
from app.claims.fees import FeeSnapshotter
from app.claims.service import ClaimService
from app.postgresdb import ClaimRepository, DbSession, ExtractionRepository, PatientRepository


def get_claim_service(session: DbSession) -> ClaimService:
    claims = ClaimRepository(session)
    return ClaimService(
        claims,
        PatientRepository(session),
        ExtractionRepository(session),
        ClaimDuplicateGuard(claims),
        FeeSnapshotter(),
    )
