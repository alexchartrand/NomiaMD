"""What an inbox row says it bills: the codes and their indicative total, so the physician
reads the day's work without opening each encounter. Never what gets billed — the claim,
saved from the review, is."""

from dataclasses import dataclass
from decimal import Decimal

from app.extraction.models import BillingExtractionResponse
from app.postgresdb import ClaimDetail


@dataclass(frozen=True)
class RowBilling:
    # Every code billed, or proposed; None when never extracted.
    code_count: int | None
    # The ones the row shows: None when never extracted, [] when none is preselected yet.
    codes: list[str] | None
    # None when no code has a dollar fee (or there are no codes).
    indicative_total: Decimal | None


class RowBillingSummarizer:
    """Once a claim exists, what it bills (the physician may have unticked or added codes).
    Before, what the review starts with ticked — the latest run's retained codes, each at its
    first fee (useCodeReview's preselection) — so the list and the review agree."""

    def summarize(self, claim: ClaimDetail | None, extraction: BillingExtractionResponse | None) -> RowBilling:
        if claim is not None:
            amounts = [code.fee_amount for code in claim.codes if code.fee_amount is not None]
            return RowBilling(len(claim.codes), [code.code for code in claim.codes], _total(amounts))
        if extraction is None:
            return RowBilling(None, None, None)
        proposed = extraction.billing.result.codes
        preselected = [code for code in proposed if code.retained]
        # A fee in "unités" counts anesthesia base units, never dollars.
        amounts = [
            Decimal(str(code.fees[0].amount))
            for code in preselected
            if code.fees and code.fees[0].unit == "dollars" and code.fees[0].amount is not None
        ]
        return RowBilling(len(proposed), [code.code for code in preselected], _total(amounts))


def _total(amounts: list[Decimal]) -> Decimal | None:
    return sum(amounts, Decimal(0)) if amounts else None
