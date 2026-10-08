"""app/benchmark/runner.py and stages.py end to end in a temp run directory: a mocked chat
model for the summary, a real RAMQCodesRetriever over a fixed-ranking code repository and a
fake embedding client — no network, no LanceDB."""

from unittest.mock import AsyncMock, patch

import pytest

from app.benchmark.commands import BenchmarkConfigError, RunCommand
from app.benchmark.query_sources import query_source
from app.benchmark.records import RetrievalRecord, SummaryRecord
from app.benchmark.runner import BenchmarkRunner
from app.benchmark.stages import RetrievalStage, SummaryStage
from app.benchmark.store import RunStore
from app.ramq_codes import build_ramq_retriever
from tests.benchmark_helpers import RankedCodeRepository, case, row
from tests.llm_helpers import FakeEmbeddingClient, fake_chat_result
from tests.test_consultation_summary import MOCK_RESULT as MOCK_SUMMARY

CASES = [
    case("CLI-1", ["A"], transcript="**NAM :** TREM 5802 1518\nSuivi de diabète."),
    case("CLI-2", ["B"], transcript="Suivi d'hypertension."),
]


def _retriever(embedding_client=None):
    codes = RankedCodeRepository([row("A", "Visites"), row("B", "Visites"), row("C", "Procédures")])
    return build_ramq_retriever(codes, embedding_client=embedding_client or FakeEmbeddingClient()), codes


def _chat(*responses):
    patcher = patch("app.extraction.engine.get_client")
    get_client = patcher.start()
    get_client.return_value.chat = AsyncMock(side_effect=list(responses))
    return patcher, get_client


async def test_a_run_stores_each_notes_summary_and_retrieval(tmp_path):
    run = RunStore(tmp_path).create("base")
    retriever, _ = _retriever()
    patcher, _ = _chat(fake_chat_result(MOCK_SUMMARY), fake_chat_result(MOCK_SUMMARY))
    try:
        progress = await BenchmarkRunner(
            [SummaryStage(), RetrievalStage(retriever, query_source("summary"))], concurrency=1
        ).run(run, CASES)
    finally:
        patcher.stop()

    assert (progress.written, progress.skipped, progress.failed) == (4, 0, [])
    summary = run.read("summary", "CLI-1", SummaryRecord)
    assert summary.result is not None and summary.model == "mistral-small-latest"
    assert {c.name for c in summary.checks} == {"date", "time_start"}

    retrieval = run.read("retrieval", "CLI-1", RetrievalRecord)
    assert retrieval.summary_run == "base"
    assert [q.source for q in retrieval.queries] == ["visit"]
    assert [c.number for c in retrieval.candidates] == ["A", "B", "C"]
    assert retrieval.candidates[0].rank == 1 and retrieval.candidates[0].rrf_score > 0


async def test_a_rerun_skips_recorded_notes_unless_forced(tmp_path):
    run = RunStore(tmp_path).create("base")
    retriever, codes = _retriever()
    stages = [RetrievalStage(retriever, query_source("transcript"))]

    await BenchmarkRunner(stages).run(run, CASES)
    second = await BenchmarkRunner(stages).run(run, CASES)
    forced = await BenchmarkRunner(stages, force=True).run(run, CASES)

    assert (second.written, second.skipped) == (0, 2)
    assert forced.written == 2
    assert len(codes.searches) == 4


async def test_the_transcript_source_needs_no_summary_and_redacts_the_nam(tmp_path):
    run = RunStore(tmp_path).create("transcript-q")
    retriever, codes = _retriever()

    await BenchmarkRunner([RetrievalStage(retriever, query_source("transcript"))]).run(run, CASES[:1])

    record = run.read("retrieval", "CLI-1", RetrievalRecord)
    assert record.error is None and record.summary_run is None
    assert [(q.source, q.text) for q in record.queries] == [("transcript", "**NAM :** [NAM]\nSuivi de diabète.")]


async def test_retrieval_reads_summaries_from_another_run(tmp_path):
    store = RunStore(tmp_path)
    base = store.create("base")
    retriever, _ = _retriever()
    patcher, _ = _chat(fake_chat_result(MOCK_SUMMARY))
    try:
        await BenchmarkRunner([SummaryStage()]).run(base, CASES[:1])
    finally:
        patcher.stop()

    sweep = store.create("sweep")
    await BenchmarkRunner([RetrievalStage(retriever, query_source("summary+transcript"), summaries=base)]).run(sweep, CASES[:1])

    record = sweep.read("retrieval", "CLI-1", RetrievalRecord)
    assert record.summary_run == "base"
    assert [q.source for q in record.queries] == ["visit", "transcript"]
    assert not sweep.has("summary", "CLI-1")


async def test_a_note_without_a_usable_summary_gets_an_error_record_not_a_crash(tmp_path):
    run = RunStore(tmp_path).create("base")
    retriever, _ = _retriever()
    patcher, _ = _chat(fake_chat_result("{not json"), fake_chat_result(MOCK_SUMMARY))
    try:
        progress = await BenchmarkRunner(
            [SummaryStage(), RetrievalStage(retriever, query_source("summary"))], concurrency=1
        ).run(run, CASES)
    finally:
        patcher.stop()

    failed_summary = run.read("summary", "CLI-1", SummaryRecord)
    assert failed_summary.error.type == "ExtractionOutputError"
    assert failed_summary.error.raw_content == "{not json"
    assert run.read("retrieval", "CLI-1", RetrievalRecord).error.type == "MissingSummary"
    assert run.read("retrieval", "CLI-2", RetrievalRecord).error is None
    assert progress.failed == ["CLI-1/summary: ExtractionOutputError", "CLI-1/retrieval: MissingSummary"]


async def test_the_summary_stage_passes_its_model_override_to_the_engine(tmp_path):
    patcher, get_client = _chat(fake_chat_result(MOCK_SUMMARY))
    try:
        await SummaryStage(model="qwen3-32b").run(CASES[0], RunStore(tmp_path).create("x"))
    finally:
        patcher.stop()

    get_client.assert_called_once_with("qwen3-32b")


@pytest.mark.parametrize(
    ("stages", "source", "summaries_from", "message"),
    [
        (["retrieval"], "summary", None, "needs summaries"),
        (["summary", "retrieval"], "summary", "base", "drop the summary stage"),
        ([], "summary", None, "No stage"),
    ],
)
def test_run_configurations_that_cannot_work_are_refused(stages, source, summaries_from, message):
    with pytest.raises(BenchmarkConfigError, match=message):
        RunCommand._validate(stages, query_source(source).needs_summary, summaries_from)
