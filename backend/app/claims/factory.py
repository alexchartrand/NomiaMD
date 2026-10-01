"""Composition root for ClaimService — wires its repositories (and the helpers built on
them) together over the request's single session, so a claim and its code rows commit or
roll back together."""

from app.auth.factory import build_profile_service
from app.claims.context import ClaimContextSnapshotter
from app.claims.duplicates import ClaimDuplicateGuard
from app.claims.fees import FeeSnapshotter
from app.claims.service import ClaimService
from app.postgresdb import (
    ClaimRepository,
    DbSession,
    EncounterRepository,
    ExtractionRepository,
    PatientRepository,
)
from app.ramq_codes import BillingContextBuilder


def get_claim_service(session: DbSession) -> ClaimService:
    claims = ClaimRepository(session)
    patients = PatientRepository(session)
    return ClaimService(
        claims,
        patients,
        ExtractionRepository(session),
        EncounterRepository(session),
        ClaimDuplicateGuard(claims),
        FeeSnapshotter(),
        ClaimContextSnapshotter(BillingContextBuilder(build_profile_service(session), patients)),
    )
