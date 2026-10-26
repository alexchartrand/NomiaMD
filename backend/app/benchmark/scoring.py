"""Scores one note's stored retrieval against its expected codes. Each expected code ends up
in exactly one bucket, checked in this order:

- exact: in the candidate list (with its rank);
- not_in_table: no such code in the codes table — a corpus gap, not a retrieval failure;
- ineligible: the code contradicts the case's billing context, so the eligibility prefilter
  removed it before ranking — a label, context or codes-table bug (the ER codes'
  `requires_registered` data bug lands here), never fixable by tuning retrieval;
- family_only: a sibling from the same `header_path` was offered (right family, wrong
  variant — usually an unresolved axis);
- not_retrieved: a real retrieval gap.

Scores are recomputed from records at report time, so labels can change without re-running
a model."""

from enum import StrEnum

from pydantic import BaseModel

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.records import RetrievalRecord
from app.lancedb import CodeRowLookupError, ICodeRepository
from app.ramq_codes import EligibilityFilterFactory


class CodeStatus(StrEnum):
    EXACT = "exact"
    FAMILY_ONLY = "family_only"
    INELIGIBLE = "ineligible"
    NOT_IN_TABLE = "not_in_table"
    NOT_RETRIEVED = "not_retrieved"


class ExpectedCodeOutcome(BaseModel):
    code: str
    status: CodeStatus
    rank: int | None = None  # 1-based, exact only
    # The query whose own hit list ranked the code highest, and that rank (1-based).
    best_query_source: str | None = None
    best_query_rank: int | None = None


class RetrievalScore(BaseModel):
    patient_id: str
    difficulty: str
    label_status: str
    is_labeled_negative: bool
    outcomes: list[ExpectedCodeOutcome]
    candidate_count: int
    query_count: int
    error: str | None = None


class RetrievalScorer:
    def __init__(self, codes: ICodeRepository, filter_factory: EligibilityFilterFactory | None = None):
        self._codes = codes
        self._filter_factory = filter_factory or EligibilityFilterFactory()

    async def score(self, case: BenchmarkCase, record: RetrievalRecord | None) -> RetrievalScore:
        error = "no retrieval record" if record is None else (record.error.type if record.error else None)
        candidates = record.candidates if record else []
        rank_by_number = {c.number: c.rank for c in candidates}
        candidate_header_paths = {c.header_path for c in candidates if c.header_path}

        outcomes = []
        for code in sorted(case.expected_codes):
            if code in rank_by_number:
                status = CodeStatus.EXACT
            else:
                status = await self._miss_status(case, code, candidate_header_paths)
            best_source, best_rank = self._best_query(record, code)
            outcomes.append(
                ExpectedCodeOutcome(
                    code=code,
                    status=status,
                    rank=rank_by_number.get(code),
                    best_query_source=best_source,
                    best_query_rank=best_rank,
                )
            )

        return RetrievalScore(
            patient_id=case.patient_id,
            difficulty=case.difficulty,
            label_status=case.label_status,
            is_labeled_negative=case.is_labeled_negative,
            outcomes=outcomes,
            candidate_count=len(candidates),
            query_count=len(record.queries) if record else 0,
            error=error,
        )

    async def _miss_status(self, case: BenchmarkCase, code: str, candidate_header_paths: set[str]) -> CodeStatus:
        try:
            row = await self._codes.get_by_number(code)
        except CodeRowLookupError:
            return CodeStatus.NOT_IN_TABLE
        eligibility = self._filter_factory.from_context(case.context)
        if not await self._codes.list_by_numbers([code], eligibility):
            return CodeStatus.INELIGIBLE
        if row.header_path and row.header_path in candidate_header_paths:
            return CodeStatus.FAMILY_ONLY
        return CodeStatus.NOT_RETRIEVED

    @staticmethod
    def _best_query(record: RetrievalRecord | None, code: str) -> tuple[str | None, int | None]:
        best: tuple[str | None, int | None] = (None, None)
        for query in record.queries if record else []:
            for rank, hit in enumerate(query.hits, start=1):
                if hit.number == code:
                    if best[1] is None or rank < best[1]:
                        best = (query.source, rank)
                    break
        return best
