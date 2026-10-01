"""`all_clean`: an encounter the physician can approve from the list, without opening it
(step 11's "Approuver les rencontres prêtes"). Computed here, never in the browser, so the
rule stays one rule."""

from app.extraction.models import BillingExtractionResponse
from app.intake import EncounterStatus


def is_all_clean(status: EncounterStatus, extraction: BillingExtractionResponse | None) -> bool:
    """Waiting for review, and every code of its latest run is high-confidence with nothing
    to confirm. No codes is not clean: there'd be nothing to approve, and an empty answer
    deserves a look."""
    if status != EncounterStatus.PRET or extraction is None:
        return False
    codes = extraction.billing.result.codes
    return bool(codes) and all(code.confidence == "high" and not code.needs_confirmation for code in codes)
