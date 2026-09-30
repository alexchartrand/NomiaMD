"""A claim's status vocabulary and the rules for moving between them — owned here, not by
the repositories, which only store whatever status they're given.

"brouillon" -> "soumis" -> "facture". "soumis" is set only when a claim is grouped onto a
generated bill (BillService.create) and reverts to "brouillon" when that bill is deleted;
"facture" is reserved for a future real RAMQ submission response and nothing sets it yet.
There's no endpoint that sets a status directly.

`Claim.status` stays a plain String column rather than a native Enum (see the Claim model's
docstring), so this StrEnum is the one place the allowed set is defined."""

from enum import StrEnum


class ClaimStatus(StrEnum):
    BROUILLON = "brouillon"
    SOUMIS = "soumis"
    FACTURE = "facture"


class ClaimLifecycle:
    """Which status a claim starts in, what a bill does to it, and what each status still
    allows. Only a draft can be billed or deleted: once a claim is on a bill it's frozen
    until that bill is deleted, so a bill's total can't shrink behind the physician's back."""

    INITIAL = ClaimStatus.BROUILLON
    ON_BILLED = ClaimStatus.SOUMIS
    ON_BILL_DELETED = ClaimStatus.BROUILLON

    @staticmethod
    def can_be_billed(status: str) -> bool:
        return status == ClaimStatus.BROUILLON

    @staticmethod
    def can_be_deleted(status: str) -> bool:
        return status == ClaimStatus.BROUILLON
