"""Shared builders for the app/benchmark tests: cases, stored records, and a code repository
whose hybrid search returns a fixed ranking (eligibility applied), so a real
RAMQCodesRetriever can run without LanceDB."""

from datetime import datetime, timezone

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.records import (
    CandidateRecord,
    QueryHitRecord,
    QueryRecord,
    RetrievalRecord,
    RunConfig,
    RunManifest,
    StageTotals,
)
from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.llm import LLMCallRecord
from app.ramq_codes import BillingContext, PatientContext
from tests.conftest import StubCodeRepository


def case(patient_id: str = "CLI-1", expected=("A",), *, difficulty="easy", label_status="reviewed", transcript="Suivi.", **context) -> BenchmarkCase:
    return BenchmarkCase(
        patient_id=patient_id,
        transcript=transcript,
        context=BillingContext(patient=PatientContext(**context)) if context else BillingContext(),
        expected_codes=frozenset(expected),
        label_status=label_status,
        difficulty=difficulty,
    )


def row(number: str, header_path: str = "", **bounds) -> CodeRow:
    return CodeRow(number=number, description=f"description {number}", header_path=header_path, **bounds)


class RankedCodeRepository(StubCodeRepository):
    """hybrid_search returns every eligible row within the query's sections, in insertion
    order, whatever the query text."""

    def __init__(self, rows: list[CodeRow]):
        super().__init__(rows)
        self.searches: list[str] = []

    async def hybrid_search(
        self,
        text: str,
        vector: list[float],
        k: int,
        eligibility: CodeEligibilityFilter | None = None,
        sections: tuple[str, ...] | None = None,
    ) -> list:
        self.searches.append(text)
        rows = [
            r
            for r in self._rows_by_number.values()
            if self._eligible(r, eligibility) and (not sections or r.header_path.startswith(sections))
        ]
        return [(r, 1.0 / (i + 1)) for i, r in enumerate(rows[:k])]


def call(*, purpose="billing_codes.retrieval", kind="embedding", model="mistral-embed", input_tokens=100, output_tokens=None, latency_ms=10.0, cached=False, error=None) -> LLMCallRecord:
    return LLMCallRecord(
        kind=kind,
        provider="mistral",
        model=model,
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        started_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        cached=cached,
        error=error,
    )


def retrieval_record(patient_id: str, ranked: list[tuple[str, str]], *, queries: list[tuple[str, list[str]]] | None = None, calls=None) -> RetrievalRecord:
    """`ranked`: (number, header_path) in candidate order; `queries`: (source, hit numbers)."""
    calls = calls or []
    return RetrievalRecord(
        patient_id=patient_id,
        calls=calls,
        totals=StageTotals.from_calls(calls, 50.0),
        query_source="summary",
        summary_run="base",
        queries=[
            QueryRecord(source=source, text=source, hits=[QueryHitRecord(number=n, relevance=1.0) for n in hits])
            for source, hits in (queries or [])
        ],
        candidates=[
            CandidateRecord(rank=i, number=n, rrf_score=1 / (60 + i), header_path=h, description=n)
            for i, (n, h) in enumerate(ranked, start=1)
        ],
    )


def manifest(name: str = "run", **config) -> RunManifest:
    now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    defaults = dict(
        stages=["summary", "retrieval"],
        llm_provider="mistral",
        embedding_provider="mistral",
        embedding_model="mistral-embed",
        codes_table="codes_test",
        similarity_top_k=20,
        fused_top_k=40,
        rrf_k=60.0,
    )
    return RunManifest(
        name=name,
        config=RunConfig(**{**defaults, **config}),
        manual_rev="test",
        git_sha="abc",
        git_dirty=False,
        argv=[],
        fixture_path="tests/fixtures/eval_billing_codes.jsonl",
        fixture_sha256="0" * 64,
        case_ids=[],
        created_at=now,
        updated_at=now,
    )
