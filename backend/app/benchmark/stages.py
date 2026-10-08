"""One benchmark stage = one step of the extraction pipeline, run on one case and turned into
a stored record. Each stage meters its own calls (usage_scope) and never raises for a
per-note failure: the error goes on the record and the run moves on to the next note, so a
flaky model fails one note, not the whole run."""

import time
from abc import ABC, abstractmethod
from dataclasses import asdict

from app.benchmark.checks import SummaryChecks
from app.benchmark.dataset import BenchmarkCase
from app.benchmark.query_sources import IQuerySource
from app.benchmark.records import (
    CandidateRecord,
    QueryHitRecord,
    QueryRecord,
    RetrievalRecord,
    StageError,
    StageName,
    StageRecord,
    StageTotals,
    SummaryRecord,
)
from app.benchmark.store import Run
from app.extraction.engine import ExtractionOutputError, run_extraction
from app.llm import usage_scope
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.summary import ConsultationSummaryTask


def _error(exc: Exception) -> StageError:
    return StageError(
        type=type(exc).__name__,
        message=str(exc),
        raw_content=exc.raw_content if isinstance(exc, ExtractionOutputError) else None,
    )


class Stage(ABC):
    name: StageName

    @abstractmethod
    async def run(self, case: BenchmarkCase, run: Run) -> StageRecord:
        pass


class SummaryStage(Stage):
    name = "summary"

    def __init__(
        self,
        model: str | None = None,
        checks: SummaryChecks | None = None,
        task: ConsultationSummaryTask | None = None,
    ):
        """`model`: None = the task's own resolution (LLM_MODEL_CONSULTATION_SUMMARY, then
        its default)."""
        self._model = model
        self._checks = checks or SummaryChecks()
        self._task = task or ConsultationSummaryTask()

    async def run(self, case: BenchmarkCase, run: Run) -> SummaryRecord:
        start = time.perf_counter()
        with usage_scope() as scope:
            try:
                extraction = await run_extraction(self._task, case.transcript, model=self._model)
            except Exception as exc:
                return SummaryRecord(
                    patient_id=case.patient_id,
                    calls=scope.records,
                    totals=StageTotals.from_calls(scope.records, (time.perf_counter() - start) * 1000),
                    error=_error(exc),
                )

        summary = extraction.result
        return SummaryRecord(
            patient_id=case.patient_id,
            calls=scope.records,
            totals=StageTotals.from_calls(scope.records, (time.perf_counter() - start) * 1000),
            model=extraction.model,
            result=summary,
            checks=self._checks.check(case, summary),
            stats=self._checks.stats(summary),
        )


class RetrievalStage(Stage):
    name = "retrieval"

    def __init__(self, retriever: RAMQCodesRetriever, query_source: IQuerySource, summaries: Run | None = None):
        """`summaries`: the run to read each note's summary from; None = the run being
        written (its own summary stage ran first)."""
        self._retriever = retriever
        self._query_source = query_source
        self._summaries = summaries

    async def run(self, case: BenchmarkCase, run: Run) -> RetrievalRecord:
        start = time.perf_counter()
        summary_run = self._summaries or run
        record = RetrievalRecord(
            patient_id=case.patient_id,
            totals=StageTotals.from_calls([], 0.0),
            query_source=self._query_source.name,
            summary_run=summary_run.name if self._query_source.needs_summary else None,
        )

        summary = None
        if self._query_source.needs_summary:
            summary_record = summary_run.read("summary", case.patient_id, SummaryRecord)
            if summary_record is None or summary_record.result is None:
                why = "no summary record" if summary_record is None else "its summary stage failed"
                record.error = StageError(type="MissingSummary", message=f"{summary_run.name}: {why}")
                return record
            summary = summary_record.result

        with usage_scope() as scope:
            try:
                trace = await self._retriever.aretrieve_queries(self._query_source.plan(case, summary), case.context)
            except Exception as exc:
                record.error = _error(exc)
                trace = None

        record.calls = scope.records
        record.totals = StageTotals.from_calls(scope.records, (time.perf_counter() - start) * 1000)
        if trace is None:
            return record

        record.queries = [
            QueryRecord(
                source=q.query.source,
                text=q.query.text,
                hits=[QueryHitRecord(number=h.number, relevance=h.relevance) for h in q.hits],
            )
            for q in trace.queries
        ]
        record.candidates = [
            CandidateRecord(
                rank=rank,
                number=f.code.number,
                rrf_score=f.rrf_score,
                header_path=f.code.header_path,
                description=f.code.description,
            )
            for rank, f in enumerate(trace.fused, start=1)
        ]
        record.unresolved_axes = list(trace.candidate_set.unresolved_axes)
        record.eligibility = asdict(trace.eligibility)
        record.embedding_ms = trace.embedding_ms
        record.db_ms = trace.db_ms
        return record
