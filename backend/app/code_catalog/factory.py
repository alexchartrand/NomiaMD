"""Composition root for CodeCatalogService, over the request's session (the billing-context
and frequent-codes reads) and the process's current codes table (registry.py)."""

from fastapi import Depends

from app.auth.factory import build_profile_service
from app.code_catalog.frequent import FrequentCodes
from app.code_catalog.registry import get_code_catalog_repository
from app.code_catalog.service import CodeCatalogService
from app.lancedb import ICodeCatalogRepository
from app.postgresdb import ClaimRepository, DbSession, PatientRepository
from app.ramq_codes import BillingContextBuilder


def get_code_catalog_service(
    session: DbSession, codes: ICodeCatalogRepository = Depends(get_code_catalog_repository)
) -> CodeCatalogService:
    return CodeCatalogService(
        codes,
        FrequentCodes(ClaimRepository(session), codes),
        BillingContextBuilder(build_profile_service(session), PatientRepository(session)),
    )
