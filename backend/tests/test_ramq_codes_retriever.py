"""Unit tests for RAMQCodesRetriever (app/ramq_codes/retriever.py), the facade over the
retrieval steps. Each step has its own tests (test_ramq_codes_query_planner.py,
test_ramq_codes_eligibility.py, test_ramq_codes_query_runner.py,
test_ramq_codes_candidate_fuser.py); this file only pins the wiring: the summary's planned
queries and the context's one eligibility filter go to the query runner, its results and
the same context go to the fuser, and the fuser's candidate set is what comes out."""

from app.care_setting import CareSetting
from app.lancedb.eligibility import CodeEligibilityFilter
from app.ramq_codes.candidate_fuser import FusedCandidate, FusedCandidates
from app.ramq_codes.context import BillingContext
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery
from app.ramq_codes.query_runner import QueryResult, QueryRun
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.summary import ConsultationSummaryResult
from tests.test_consultation_summary import MOCK_RESULT

SUMMARY = ConsultationSummaryResult.model_validate(MOCK_RESULT)
_FILTER = CodeEligibilityFilter(age=45)
_QUERIES = [PlannedQuery("visite", "visit"), PlannedQuery("ECG", "procedure")]
_RESULTS = [QueryResult(query=q, hits=[]) for q in _QUERIES]
_FUSED = FusedCandidates(ranked=[FusedCandidate(code=Code(number="A", description=""), rrf_score=0.1)], unresolved_axes=("panel_size",))


class _FakeQueryPlanner:
    def __init__(self):
        self.calls: list[tuple[ConsultationSummaryResult, CareSetting | None]] = []

    def plan_labeled(self, summary: ConsultationSummaryResult, care_setting: CareSetting | None) -> list[PlannedQuery]:
        self.calls.append((summary, care_setting))
        return _QUERIES


class _FakeFilterFactory:
    def __init__(self):
        self.calls: list[BillingContext] = []

    def from_context(self, context: BillingContext) -> CodeEligibilityFilter:
        self.calls.append(context)
        return _FILTER


class _FakeQueryRunner:
    def __init__(self):
        self.calls: list[tuple[list[PlannedQuery], CodeEligibilityFilter]] = []

    async def run(self, queries: list[PlannedQuery], eligibility: CodeEligibilityFilter) -> QueryRun:
        self.calls.append((queries, eligibility))
        return QueryRun(results=_RESULTS, embedding_ms=0.0, db_ms=0.0)


class _FakeCandidateFuser:
    def __init__(self):
        self.calls: list[tuple[list[QueryResult], BillingContext]] = []

    def fuse(self, results: list[QueryResult], context: BillingContext) -> FusedCandidates:
        self.calls.append((results, context))
        return _FUSED


async def test_aretrieve_composes_planner_filter_runner_and_fuser():
    planner, factory, runner, fuser = _FakeQueryPlanner(), _FakeFilterFactory(), _FakeQueryRunner(), _FakeCandidateFuser()
    retriever = RAMQCodesRetriever(runner, fuser, query_planner=planner, filter_factory=factory)
    context = BillingContext()

    result = await retriever.aretrieve(SUMMARY, context)

    assert planner.calls == [(SUMMARY, None)]
    assert factory.calls == [context]
    assert runner.calls == [(_QUERIES, _FILTER)]
    assert fuser.calls == [(_RESULTS, context)]
    assert result == _FUSED.candidate_set


async def test_aretrieve_plans_with_the_contexts_care_setting():
    planner = _FakeQueryPlanner()
    retriever = RAMQCodesRetriever(
        _FakeQueryRunner(), _FakeCandidateFuser(), query_planner=planner, filter_factory=_FakeFilterFactory()
    )

    await retriever.aretrieve(SUMMARY, BillingContext(care_setting=CareSetting.URGENCE))

    assert planner.calls == [(SUMMARY, CareSetting.URGENCE)]
