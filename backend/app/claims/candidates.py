"""The codes a stored billing_codes extraction offered the physician — what a suggested
code's description/confidence/explanation/fees are snapshotted from (never the request body;
a code the physician added by hand is snapshotted from the codes table instead, see
catalog.py).

Validates just the fields a claim snapshots rather than the full BillingCodesResult: older
stored results predate fields like `supporting_quote`, and a claim doesn't need them."""

from pydantic import BaseModel

from app.claims.origin import CodeOrigin
from app.ramq_codes import CodeFeeOut


class StoredCandidate(BaseModel):
    code: str
    description: str
    # None for a code the physician added by hand — it was never scored.
    confidence: str | None
    explanation: str
    fees: list[CodeFeeOut] = []
    # Not carried by extraction results yet (see BACKLOG.md's manual_rev item).
    manual_rev: str | None = None
    origin: CodeOrigin = CodeOrigin.SUGGESTED


class _StoredBillingResult(BaseModel):
    codes: list[StoredCandidate] = []


class ExtractionCandidates:
    def __init__(self, candidates: list[StoredCandidate]):
        # First occurrence wins if the model ever returned the same code twice.
        self._by_code: dict[str, StoredCandidate] = {}
        for candidate in candidates:
            self._by_code.setdefault(candidate.code, candidate)

    @classmethod
    def from_result_json(cls, result_json: dict) -> "ExtractionCandidates":
        return cls(_StoredBillingResult.model_validate(result_json).codes)

    def get(self, code: str) -> StoredCandidate | None:
        return self._by_code.get(code)
