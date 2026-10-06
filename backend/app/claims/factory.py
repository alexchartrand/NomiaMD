"""Composition roots for ClaimService and ManualClaimService — wire their repositories (and the
helpers built on them) together over the request's single session, so a claim and its code
rows commit or roll back together. A code added by hand is read from the process's current
codes table (app/code_catalog/registry.py)."""

from fastapi import Depends

from app.auth.factory import build_profile_service
from app.claims.catalog import CatalogCodes
from app.claims.code_resolver import ClaimCodeResolver
from app.claims.context import ClaimContextSnapshotter
from app.claims.duplicates import ClaimDuplicateGuard
from app.claims.lines import ClaimLineBuilder
from app.claims.manual import ManualClaimService
from app.claims.service import ClaimService
from app.code_catalog import get_code_catalog_repository
from app.lancedb import ICodeCatalogRepository
from app.postgresdb import (
    ClaimRepository,
    DbSession,
    EncounterRepository,
    ExtractionRepository,
    PatientRepository,
)
from app.ramq_codes import BillingContextBuilder


def _context_snapshotter(session: DbSession, patients: PatientRepository) -> ClaimContextSnapshotter:
    return ClaimContextSnapshotter(BillingContextBuilder(build_profile_service(session), patients))


def get_claim_service(
    session: DbSession, codes: ICodeCatalogRepository = Depends(get_code_catalog_repository)
) -> ClaimService:
    claims = ClaimRepository(session)
    patients = PatientRepository(session)
    return ClaimService(
        claims,
        patients,
        ExtractionRepository(session),
        EncounterRepository(session),
        ClaimDuplicateGuard(claims),
        ClaimLineBuilder(),
        _context_snapshotter(session, patients),
        ClaimCodeResolver(CatalogCodes(codes)),
    )


def get_manual_claim_service(
    session: DbSession, codes: ICodeCatalogRepository = Depends(get_code_catalog_repository)
) -> ManualClaimService:
    patients = PatientRepository(session)
    return ManualClaimService(
        ClaimRepository(session),
        patients,
        CatalogCodes(codes),
        ClaimLineBuilder(),
        _context_snapshotter(session, patients),
    )
