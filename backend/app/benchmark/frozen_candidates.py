"""The selection stage's candidates: a stored retrieval result read back instead of searching,
so the billing_codes call can be benchmarked on frozen candidates — another model's
selection on the very same candidate list, or one retrieval run reused across many
selection runs with no embedding call."""

from collections.abc import Sequence

from app.lancedb import ICodeRepository
from app.ramq_codes import CandidateSet, CodesRowConverter


class FrozenCandidatesError(LookupError):
    """A stored candidate is missing from the codes table: the run was retrieved from
    another table than the one being read."""


class FrozenCandidatesLoader:
    def __init__(self, codes: ICodeRepository, converter: CodesRowConverter | None = None):
        self._codes = codes
        self._converter = converter or CodesRowConverter()

    async def load(self, numbers: Sequence[str], unresolved_axes: Sequence[str] = ()) -> CandidateSet:
        """`numbers`: the stored candidates, in rank order. They were eligibility-filtered
        when retrieved, so they're read back without a filter."""
        rows = {row.number: row for row in await self._codes.list_by_numbers(list(numbers))}
        missing = [n for n in numbers if n not in rows]
        if missing:
            raise FrozenCandidatesError(f"Candidate(s) not in the codes table: {', '.join(missing)}")
        return CandidateSet(
            candidates=[self._converter.convert(rows[n]) for n in numbers],
            unresolved_axes=tuple(unresolved_axes),
        )
