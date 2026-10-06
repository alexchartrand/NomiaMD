"""The codes the physician added by hand, read from the current codes table — what such a
code's description and fees are snapshotted from, never the request body. Eligibility is
enforced here, not just in the search UI: a code whose variants all contradict a known fact
about the patient is refused like an unknown one."""

from app.claims.candidates import StoredCandidate
from app.claims.errors import IneligibleOrUnknownCodesError
from app.claims.origin import CodeOrigin
from app.lancedb import CodeEligibilityFilter, ICodeCatalogRepository
from app.lancedb.models import CodeRow
from app.ramq_codes import CodeFeeOut


class CatalogCodes:
    def __init__(self, codes: ICodeCatalogRepository):
        self._codes = codes

    async def require(self, numbers: list[str], eligibility: CodeEligibilityFilter) -> list[StoredCandidate]:
        """The candidate for each of `numbers`, in order — raises
        IneligibleOrUnknownCodesError naming every one that isn't billable for this patient."""
        if not numbers:
            return []
        rows = {row.number: row for row in await self._codes.list_by_numbers(numbers, eligibility)}
        refused = [number for number in numbers if number not in rows]
        if refused:
            raise IneligibleOrUnknownCodesError(refused)
        revision = await self._codes.current_revision()
        return [self._candidate(rows[number], revision) for number in numbers]

    @staticmethod
    def _candidate(row: CodeRow, revision: str) -> StoredCandidate:
        return StoredCandidate(
            code=row.number,
            description=row.description,
            confidence=None,
            explanation="",
            fees=[CodeFeeOut.model_validate(fee.model_dump()) for fee in row.fees],
            manual_rev=revision,
            origin=CodeOrigin.MANUAL,
        )
