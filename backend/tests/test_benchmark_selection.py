"""Phase 2 of app/benchmark: the selection stage over frozen candidates
(frozen_candidates.py, recording_task.py, stages.py's SelectionStage), its scoring
(selection_scoring.py), and how it aggregates, compares and renders — with a mocked chat
model and a stub code repository."""

from unittest.mock import AsyncMock, patch

import pytest

from app.benchmark.aggregate import RunAggregator
from app.benchmark.commands import BenchmarkConfigError, RunCommand
from app.benchmark.compare import SelectionComparator
from app.benchmark.frozen_candidates import FrozenCandidatesError, FrozenCandidatesRetriever
from app.benchmark.query_sources import query_source
from app.benchmark.records import SelectionRecord, StageTotals, SummaryRecord
from app.benchmark.report import MarkdownReport
from app.benchmark.runner import BenchmarkRunner
from app.benchmark.selection_scoring import ExpectedStatus, SelectionScorer
from app.benchmark.stages import SelectionStage
from app.benchmark.store import RunStore
from app.ramq_codes import BillingContext
from app.ramq_codes.context import AXIS_LABELS_FR, AXIS_PANEL_SIZE
from app.summary import ConsultationSummaryResult
from tests.benchmark_helpers import (
    RankedCodeRepository,
    case,
    extracted,
    manifest,
    retrieval_record,
    row,
    selection_record,
)
from tests.llm_helpers import fake_chat_result
from tests.test_consultation_summary import MOCK_RESULT as MOCK_SUMMARY

CODES = RankedCodeRepository([
    row("A", "Visites > Suivi"),
    row("A2", "Visites > Suivi"),
    row("B", "Procédures > ECG"),
    row("C", "Procédures > Plâtre"),
])


def _summary_record(patient_id: str) -> SummaryRecord:
    return SummaryRecord(
        patient_id=patient_id,
        totals=StageTotals.from_calls([], 1.0),
        result=ConsultationSummaryResult.model_validate(MOCK_SUMMARY),
    )


def _base_run(tmp_path, name="base", patient_id="CLI-1", ranked=(("A", "Visites > Suivi"), ("B", "Procédures > ECG"))):
    """A run holding one note's summary and retrieval records."""
    run = RunStore(tmp_path).create(name)
    run.write("summary", _summary_record(patient_id))
    record = retrieval_record(patient_id, list(ranked))
    record.unresolved_axes = [AXIS_PANEL_SIZE]
    run.write("retrieval", record)
    return run


def _chat(*responses):
    patcher = patch("app.extraction.engine.get_client")
    get_client = patcher.start()
    get_client.return_value.chat = AsyncMock(side_effect=list(responses))
    return patcher, get_client


# --- FrozenCandidatesRetriever


async def test_frozen_candidates_come_back_in_their_stored_rank_with_their_axes():
    retriever = FrozenCandidatesRetriever(CODES, ["B", "A"], [AXIS_PANEL_SIZE])

    candidates = await retriever.aretrieve(ConsultationSummaryResult.model_validate(MOCK_SUMMARY), BillingContext())

    assert [c.number for c in candidates.candidates] == ["B", "A"]
    assert candidates.candidates[1].header_path == "Visites > Suivi"
    assert candidates.unresolved_axes == (AXIS_PANEL_SIZE,)


async def test_a_frozen_candidate_missing_from_the_table_is_an_error_not_a_shorter_list():
    with pytest.raises(FrozenCandidatesError, match="ZZZ"):
        await FrozenCandidatesRetriever(CODES, ["A", "ZZZ"]).aretrieve(
            ConsultationSummaryResult.model_validate(MOCK_SUMMARY), BillingContext()
        )


# --- SelectionStage


async def test_selection_runs_billing_codes_on_the_stored_candidates_and_records_what_parse_dropped(tmp_path):
    run = _base_run(tmp_path)
    answer = {"analysis": "Suivi.", "codes": [extracted("A"), "B"], "other_possible_codes": [extracted("ZZZ")], "notes": None}
    patcher, get_client = _chat(fake_chat_result(answer, model="mistral-medium-latest"))
    try:
        progress = await BenchmarkRunner([SelectionStage(CODES)]).run(run, [case("CLI-1", ["A"])])
    finally:
        patcher.stop()

    assert progress.failed == []
    record = run.read("selection", "CLI-1", SelectionRecord)
    assert (record.candidates_run, record.summary_run) == ("base", "base")
    assert record.offered == ["A", "B"]
    assert [(c.code, c.retained) for c in record.result.codes] == [("A", True)]
    assert record.result.analysis == "Suivi."
    assert (record.raw_code_count, record.dropped_not_offered, record.dropped_malformed) == (3, ["ZZZ"], 1)
    assert record.model == "mistral-medium-latest"
    assert record.prompt_chars > 0

    user_message = get_client.return_value.chat.call_args.kwargs["messages"][1].content
    assert "- A | Visites > Suivi" in user_message and "- B | Procédures > ECG" in user_message
    assert AXIS_LABELS_FR[AXIS_PANEL_SIZE] in user_message


async def test_selection_reads_candidates_and_summaries_from_other_runs_with_its_own_model(tmp_path):
    base = _base_run(tmp_path)
    run = RunStore(tmp_path).create("qwen-sel")
    patcher, get_client = _chat(fake_chat_result({"codes": [], "notes": None}))
    try:
        stage = SelectionStage(CODES, candidates=base, summaries=base, model="qwen3-32b")
        await BenchmarkRunner([stage]).run(run, [case("CLI-1", ["A"])])
    finally:
        patcher.stop()

    record = run.read("selection", "CLI-1", SelectionRecord)
    assert record.error is None and record.result.codes == []
    assert (record.candidates_run, record.summary_run) == ("base", "base")
    get_client.assert_called_once_with("qwen3-32b")
    assert not run.has("retrieval", "CLI-1")


async def test_a_note_without_candidates_gets_an_error_record_and_no_model_call(tmp_path):
    run = RunStore(tmp_path).create("base")
    run.write("summary", _summary_record("CLI-1"))
    patcher, get_client = _chat()
    try:
        progress = await BenchmarkRunner([SelectionStage(CODES)]).run(run, [case("CLI-1", ["A"])])
    finally:
        patcher.stop()

    assert run.read("selection", "CLI-1", SelectionRecord).error.type == "MissingCandidates"
    assert progress.failed == ["CLI-1/selection: MissingCandidates"]
    get_client.return_value.chat.assert_not_called()


async def test_an_unusable_answer_keeps_its_raw_content_and_the_offered_list(tmp_path):
    run = _base_run(tmp_path)
    patcher, _ = _chat(fake_chat_result("{not json"))
    try:
        await BenchmarkRunner([SelectionStage(CODES)]).run(run, [case("CLI-1", ["A"])])
    finally:
        patcher.stop()

    record = run.read("selection", "CLI-1", SelectionRecord)
    assert record.error.type == "ExtractionOutputError" and record.error.raw_content == "{not json"
    assert record.offered == ["A", "B"] and record.result is None


# --- SelectionScorer


async def _score(expected, offered, returned, **kwargs):
    return await SelectionScorer(CODES).score(
        case("CLI-1", expected, **kwargs.pop("case_kwargs", {})), selection_record("CLI-1", offered, returned, **kwargs)
    )


async def test_each_expected_code_is_retained_possible_left_out_or_not_offered():
    score = await _score(
        ["A", "B", "C", "D"], ["A", "B", "C"], [extracted("A"), extracted("B", "medium", retained=False)]
    )

    assert {o.code: o.status for o in score.expected} == {
        "A": ExpectedStatus.RETAINED,
        "B": ExpectedStatus.POSSIBLE,
        "C": ExpectedStatus.OFFERED_NOT_SELECTED,
        "D": ExpectedStatus.NOT_OFFERED,
    }
    assert (score.true_positives, score.found_overall) == (1, 2)


async def test_an_exact_note_is_judged_on_the_retained_codes_only():
    score = await _score(["A"], ["A", "B"], [extracted("A"), extracted("B", "low", retained=False)])

    assert score.exact_match


async def test_a_wrong_code_from_an_expected_codes_family_is_a_wrong_variant():
    score = await _score(["A"], ["A", "A2", "B"], [extracted("A2"), extracted("B", "low")])

    outcomes = {o.code: o for o in score.returned}
    assert (outcomes["A2"].correct, outcomes["A2"].wrong_variant_of) == (False, "A")
    assert (outcomes["B"].correct, outcomes["B"].wrong_variant_of) == (False, None)


async def test_a_labeled_negative_is_clean_only_when_nothing_comes_back_in_either_tier():
    clean = await _score([], ["A"], [])
    possible = await _score([], ["A"], [extracted("A", "low", retained=False)])

    assert clean.is_labeled_negative and clean.clean_negative
    assert not possible.clean_negative and possible.returned[0].correct is False


async def test_an_unlabeled_note_never_judges_its_codes():
    score = await _score([], ["A"], [extracted("A")], case_kwargs={"label_status": "needs_physician_label"})

    assert not score.is_labeled and score.returned[0].correct is None


# --- aggregate, compare, report


async def _scores():
    scorer = SelectionScorer(CODES)
    return [
        # A retained, B only possible, plus a retained wrong variant
        await scorer.score(
            case("N1", ["A", "B"]),
            selection_record("N1", ["A", "A2", "B"], [extracted("A"), extracted("A2", "medium"), extracted("B", "medium", retained=False)]),
        ),
        # exact on its retained code, a wrong possible one, and one invented code dropped
        await scorer.score(
            case("N2", ["B"], difficulty="hard"),
            selection_record("N2", ["B", "C"], [extracted("B", "high", ["confirmer"]), extracted("C", "low", retained=False)], dropped_not_offered=["ZZZ"]),
        ),
        # labeled negatives: one clean, one with a possible code
        await scorer.score(case("N3", [], difficulty="negative"), selection_record("N3", ["A"], [])),
        await scorer.score(case("N4", [], difficulty="negative"), selection_record("N4", ["A"], [extracted("A", "low", retained=False)])),
    ]


async def test_selection_metrics_judge_precision_on_retained_codes_and_report_overall_recall():
    m = RunAggregator().aggregate([], [], [], selection_scores=await _scores()).selection

    assert (m.expected_positions, m.returned_codes, m.true_positives) == (3, 3, 2)
    assert round(m.precision, 3) == round(2 / 3, 3) and round(m.recall, 3) == round(2 / 3, 3)
    assert round(m.f1, 3) == round(2 / 3, 3)
    assert (m.macro_recall, m.exact_match_rate, m.overall_recall) == (0.75, 0.5, 1.0)
    assert m.status_counts == {"retained": 2, "possible": 1, "offered_not_selected": 0, "not_offered": 0}
    assert m.wrong_variants == 1
    assert (m.mean_retained, m.mean_possible) == (0.75, 0.75)
    assert (m.negatives, m.clean_negatives) == (2, 1)
    assert m.by_confidence["retained"]["high"].precision == 1.0
    assert m.by_confidence["retained"]["medium"].correct == 0
    assert (m.by_confidence["possible"]["medium"].returned, m.by_confidence["possible"]["medium"].correct) == (1, 1)
    assert m.needs_confirmation_rate == 1 / 6
    assert (m.invented_codes, m.notes_with_invented_codes, m.invented_rate) == (1, 1, 1 / 7)


async def test_the_comparison_lists_retained_and_overall_changes_note_by_note():
    before = await _scores()
    scorer = SelectionScorer(CODES)
    after = [
        # B moves from possible to retained, the wrong variant goes away
        await scorer.score(case("N1", ["A", "B"]), selection_record("N1", ["A", "B"], [extracted("A"), extracted("B")])),
        # B is no longer returned at all, a wrong code is retained instead
        await scorer.score(case("N2", ["B"], difficulty="hard"), selection_record("N2", ["B"], [extracted("C")])),
    ]

    comparison = SelectionComparator().compare("base", before, "new", after)

    by_note = {n.patient_id: n for n in comparison.notes}
    n1, n2 = by_note["N1"], by_note["N2"]
    assert (n1.verdict, n1.gained, n1.fixed_wrong, n1.gained_overall) == ("improved", ["B"], ["A2"], [])
    assert (n2.verdict, n2.lost, n2.new_wrong, n2.lost_overall) == ("regressed", ["B"], ["C"], ["B"])
    assert comparison.notes[0].patient_id == "N2"


async def test_the_report_has_a_selection_section_and_per_note_table():
    scores = await _scores()
    records = [selection_record("N1", ["A"], [extracted("A")])]
    metrics = RunAggregator().aggregate([], [], [], records, scores)

    text = MarkdownReport().render(manifest(stages=["selection"], candidates_from="base"), metrics, [], None, scores)

    assert "## Selection" in text and "## Selection per note" in text
    assert "| candidates from | base |" in text
    assert "A2 (variant of A)" in text and "B ~ possible" in text


# --- RunCommand validation


@pytest.mark.parametrize(
    ("stages", "summaries_from", "candidates_from", "message"),
    [
        (["summary", "selection"], None, None, "needs candidates"),
        (["retrieval", "selection"], "s", "base", "drop the retrieval stage"),
        (["summary"], None, "base", "only feeds the selection stage"),
        (["selection"], None, None, "needs candidates"),
    ],
)
def test_selection_configurations_that_cannot_work_are_refused(stages, summaries_from, candidates_from, message):
    with pytest.raises(BenchmarkConfigError, match=message):
        RunCommand._validate(stages, query_source("summary").needs_summary, summaries_from, candidates_from)


def test_a_selection_only_run_reads_summaries_where_its_candidates_did():
    assert RunCommand._summaries_of("base", manifest(stages=["summary", "retrieval"]).config) == "base"
    assert RunCommand._summaries_of("sweep", manifest(stages=["retrieval"], summaries_from="base").config) == "base"
    with pytest.raises(BenchmarkConfigError, match="--summaries-from"):
        RunCommand._summaries_of("t", manifest(stages=["retrieval"], query_source="transcript").config)


def test_a_selection_only_run_reads_the_table_its_candidates_came_from():
    retrieved = manifest(codes_table="codes_a").config

    assert RunCommand._candidates_table(None, retrieved) == "codes_a"
    with pytest.raises(BenchmarkConfigError, match="codes_a"):
        RunCommand._candidates_table("codes_b", retrieved)


def test_selection_without_a_summary_source_is_refused_up_front():
    """The full pipeline minus the summary stage, with no run to read summaries from."""
    with pytest.raises(BenchmarkConfigError, match="needs summaries"):
        RunCommand._validate(["retrieval", "selection"], False, None, None)
