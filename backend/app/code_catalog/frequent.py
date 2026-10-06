"""The codes a physician bills most — what the code search offers before anything is typed."""

from app.lancedb import CodeEligibilityFilter, ICodeCatalogRepository
from app.lancedb.models import CodeRow
from app.postgresdb import ClaimRepository


class FrequentCodes:
    def __init__(self, claims: ClaimRepository, codes: ICodeCatalogRepository):
        self._claims = claims
        self._codes = codes

    async def for_physician(
        self, physician_id: int, limit: int, eligibility: CodeEligibilityFilter | None = None
    ) -> list[CodeRow]:
        """Re-read from the current codes table, so a code retired by a newer manual revision
        (or ineligible for this patient) drops out, while the physician's ranking is kept."""
        numbers = await self._claims.most_used_codes(physician_id, limit)
        rows = {row.number: row for row in await self._codes.list_by_numbers(numbers, eligibility)}
        return [rows[number] for number in numbers if number in rows]
