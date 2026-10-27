"""A claim's status vocabulary and the rules that go with it — owned here, not by the
repositories.

Status is derived, never stored: a claim is "soumis" exactly when it's on a bill
(`Claim.bill_id IS NOT NULL`) and "brouillon" otherwise. It becomes "soumis" when
BillService.create attaches it to a bill, and goes back to "brouillon" when that bill is
voided. A future real RAMQ submission response would add its own state — with its own
column, since the bill link can't express it."""

from enum import StrEnum
from typing import Protocol


class ClaimStatus(StrEnum):
    BROUILLON = "brouillon"
    SOUMIS = "soumis"


class Billable(Protocol):
    """A Claim, or a ShiftClaim (app/shift_claims/): both are billed the same way."""

    bill_id: int | None


class ClaimLifecycle:
    """What each status is, and what it still allows. Only a draft can be billed or voided:
    once a claim is on a bill it's frozen until that bill is voided, so a bill's total can't
    shrink behind the physician's back."""

    @staticmethod
    def status_of(claim: Billable) -> ClaimStatus:
        return ClaimStatus.SOUMIS if claim.bill_id is not None else ClaimStatus.BROUILLON

    @staticmethod
    def is_billed(status: ClaimStatus) -> bool:
        """The storage-level filter a status stands for — see ClaimRepository.list_for_physician."""
        return status == ClaimStatus.SOUMIS

    @classmethod
    def can_be_billed(cls, claim: Billable) -> bool:
        return cls.status_of(claim) == ClaimStatus.BROUILLON

    @classmethod
    def can_be_voided(cls, claim: Billable) -> bool:
        return cls.status_of(claim) == ClaimStatus.BROUILLON
