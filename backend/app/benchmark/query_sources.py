"""What a retrieval run searches with. `summary` is what production does; `transcript` and
`summary+transcript` are control runs: how much does the structured summary add over the
raw note, and does adding the note's own query on top help?"""

from abc import ABC, abstractmethod

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.records import QuerySourceName
from app.ramq_codes.query_planner import PlannedQuery, SummaryQueryPlanner, TranscriptQueryPlanner
from app.summary import ConsultationSummaryResult


class IQuerySource(ABC):
    name: QuerySourceName
    needs_summary: bool

    @abstractmethod
    def plan(self, case: BenchmarkCase, summary: ConsultationSummaryResult | None) -> list[PlannedQuery]:
        pass


class SummaryQuerySource(IQuerySource):
    name = "summary"
    needs_summary = True

    def __init__(self, planner: SummaryQueryPlanner | None = None):
        self._planner = planner or SummaryQueryPlanner()

    def plan(self, case: BenchmarkCase, summary: ConsultationSummaryResult | None) -> list[PlannedQuery]:
        if summary is None:
            raise ValueError(f"The {self.name!r} query source needs the note's summary")
        return self._planner.plan_labeled(summary, case.context.care_setting)


class TranscriptQuerySource(IQuerySource):
    name = "transcript"
    needs_summary = False

    def __init__(self, planner: TranscriptQueryPlanner | None = None):
        self._planner = planner or TranscriptQueryPlanner()

    def plan(self, case: BenchmarkCase, summary: ConsultationSummaryResult | None) -> list[PlannedQuery]:
        return self._planner.plan(case.transcript)


class CombinedQuerySource(IQuerySource):
    name = "summary+transcript"
    needs_summary = True

    def __init__(self):
        self._summary = SummaryQuerySource()
        self._transcript = TranscriptQuerySource()

    def plan(self, case: BenchmarkCase, summary: ConsultationSummaryResult | None) -> list[PlannedQuery]:
        return [*self._summary.plan(case, summary), *self._transcript.plan(case, summary)]


QUERY_SOURCES: dict[str, type[IQuerySource]] = {
    "summary": SummaryQuerySource,
    "transcript": TranscriptQuerySource,
    "summary+transcript": CombinedQuerySource,
}


def query_source(name: str) -> IQuerySource:
    return QUERY_SOURCES[name]()
