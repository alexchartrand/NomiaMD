"""The selection stage's retriever: replays a stored retrieval result instead of searching,
so the billing_codes call can be benchmarked on frozen candidates — another model's
selection on the very same candidate list, or one retrieval run reused across many
selection runs with no embedding call."""

from collections.abc import Sequence

from app.lancedb import ICodeRepository
from app.ramq_codes import CodesRowConverter
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.retriever import ICodesRetriever
from app.summary import ConsultationSummaryResult


class FrozenCandidatesError(LookupError):
    """A stored candidate is missing from the codes table: the run was retrieved from
    another table than the one being read."""


class FrozenCandidatesRetriever(ICodesRetriever):
    def __init__(
        self,
        codes: ICodeRepository,
        numbers: Sequence[str],
        unresolved_axes: Sequence[str] = (),
        converter: CodesRowConverter | None = None,
    ):
        """`numbers`: the stored candidates, in rank order. They were eligibility-filtered
        when retrieved, so they're read back without a filter."""
        self._codes = codes
        self._numbers = list(numbers)
        self._unresolved_axes = tuple(unresolved_axes)
        self._converter = converter or CodesRowConverter()

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        rows = {row.number: row for row in await self._codes.list_by_numbers(self._numbers)}
        missing = [n for n in self._numbers if n not in rows]
        if missing:
            raise FrozenCandidatesError(f"Candidate(s) not in the codes table: {', '.join(missing)}")
        return CandidateSet(
            candidates=[self._converter.convert(rows[n]) for n in self._numbers],
            unresolved_axes=self._unresolved_axes,
        )
