"""Composition root for ShiftClaimService, over the request's single session. The catalog is
read once per process (`shift_code_catalog`), and checked at startup by app/bootstrap.py."""

from functools import lru_cache

from app.postgresdb import DbSession, ShiftClaimRepository, ShiftRepository, WorkSiteRepository
from app.shift_claims.catalog import ShiftCodeCatalog
from app.shift_claims.lines import ShiftClaimLineBuilder
from app.shift_claims.pending import UnclaimedShifts
from app.shift_claims.rules import ShiftCodeRules
from app.shift_claims.service import ShiftClaimService


@lru_cache(maxsize=1)
def shift_code_catalog() -> ShiftCodeCatalog:
    return ShiftCodeCatalog()


def get_shift_claim_service(session: DbSession) -> ShiftClaimService:
    catalog = shift_code_catalog()
    return ShiftClaimService(
        ShiftRepository(session),
        WorkSiteRepository(session),
        ShiftClaimRepository(session),
        catalog,
        ShiftCodeRules(catalog),
        ShiftClaimLineBuilder(catalog),
    )


def unclaimed_shifts(session: DbSession) -> UnclaimedShifts:
    return UnclaimedShifts(ShiftRepository(session), ShiftClaimRepository(session), ShiftCodeRules(shift_code_catalog()))
