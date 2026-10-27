"""`all_clean`: an encounter the physician can approve from the list, without opening it
(step 11's "Approuver les rencontres prêtes"). Computed here, never in the browser, so the
rule stays one rule."""

from datetime import date

from app.extraction.models import BillingExtractionResponse
from app.intake import EncounterStatus


def is_all_clean(
    status: EncounterStatus,
    extraction: BillingExtractionResponse | None,
    *,
    service_date: date | None,
    possible_duplicate: bool,
    setting_unsettled: bool = False,
) -> bool:
    """Waiting for review, and every code its latest run retained (what approving bills) is
    high-confidence with nothing to confirm and at most one fee (several means the physician
    picks one). The other possible codes don't count: approving leaves them out. No retained
    code is not clean: there'd be nothing to approve, and an empty answer deserves a look.
    Nor is an undated one (a claim needs its date) or a possible duplicate, until the
    physician says whether it's the same visit. Nor one whose shift is still to choose, or
    changed since its codes were chosen (`setting_unsettled`): they may be the wrong ones."""
    if (
        status != EncounterStatus.PRET
        or extraction is None
        or service_date is None
        or possible_duplicate
        or setting_unsettled
    ):
        return False
    codes = [code for code in extraction.billing.codes if code.retained]
    return bool(codes) and all(
        code.confidence == "high" and not code.needs_confirmation and len(code.fees) <= 1 for code in codes
    )
