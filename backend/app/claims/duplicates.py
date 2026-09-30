"""The two duplicate-claim rules, which differ in whether the physician may override them."""

from datetime import date

from app.claims.errors import DuplicateClaimError
from app.postgresdb import ClaimRepository

EXTRACTION_ALREADY_CLAIMED = "Cette extraction a déjà été enregistrée comme facturation."
SAME_PATIENT_SAME_DAY = "Une facturation existe déjà pour ce patient à cette date."


class ClaimDuplicateGuard:
    def __init__(self, claim_repository: ClaimRepository):
        self._claim_repository = claim_repository

    async def ensure_extraction_unclaimed(self, billing_extraction_record_id: int) -> None:
        """Never overridable — resubmitting the exact same extraction as a second claim is
        a client bug, not a legitimate re-bill. The billing_extraction_record_id unique
        constraint is the backstop for two requests racing past this check
        (ClaimRepository.create raises ExtractionAlreadyClaimedError)."""
        if await self._claim_repository.get_by_billing_extraction_record_id(billing_extraction_record_id):
            raise DuplicateClaimError(EXTRACTION_ALREADY_CLAIMED)

    async def ensure_first_on_date(self, physician_id: int, patient_id: int, service_date: date) -> None:
        """A warning the caller can override (confirm_duplicate) — a physician can
        legitimately bill the same patient twice in one day."""
        if await self._claim_repository.count_for_patient_on_date(physician_id, patient_id, service_date):
            raise DuplicateClaimError(SAME_PATIENT_SAME_DAY)
