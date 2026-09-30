"""The codes a stored billing_codes extraction offered the physician — the only source a
claim's description/confidence/explanation/fees are ever snapshotted from (never the request
body).

Validates just the fields a claim snapshots rather than the full BillingCodesResult: older
stored results predate fields like `supporting_quote`, and a claim doesn't need them."""

from pydantic import BaseModel

from app.claims.errors import UnknownCodesError
from app.ramq_codes import CodeFeeOut


class StoredCandidate(BaseModel):
    code: str
    description: str
    confidence: str
    explanation: str
    fees: list[CodeFeeOut] = []


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

    def require(self, codes: list[str]) -> list[StoredCandidate]:
        """The candidate for each of `codes`, in order — raises UnknownCodesError naming
        every code this extraction never offered."""
        unknown = [code for code in codes if code not in self._by_code]
        if unknown:
            raise UnknownCodesError(unknown)
        return [self._by_code[code] for code in codes]
