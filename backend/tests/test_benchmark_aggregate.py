"""app/benchmark/aggregate.py, compare.py and report.py over hand-made scores and records."""

from app.benchmark.aggregate import LatencyStats, RunAggregator
from app.benchmark.compare import RunComparator
from app.benchmark.records import StageTotals, SummaryCheck, SummaryRecord
from app.benchmark.report import MarkdownReport
from app.benchmark.scoring import CodeStatus, ExpectedCodeOutcome, RetrievalScore
from tests.benchmark_helpers import call, manifest, retrieval_record


def _score(patient_id: str, outcomes: list[tuple[str, CodeStatus, int | None]], *, difficulty="easy", candidates=10) -> RetrievalScore:
    return RetrievalScore(
        patient_id=patient_id,
        difficulty=difficulty,
        label_status="reviewed",
        is_labeled_negative=not outcomes,
        outcomes=[ExpectedCodeOutcome(code=c, status=s, rank=r) for c, s, r in outcomes],
        candidate_count=candidates,
        query_count=2,
    )


SCORES = [
    _score("N1", [("A", CodeStatus.EXACT, 1), ("B", CodeStatus.EXACT, 15)]),
    _score("N2", [("C", CodeStatus.FAMILY_ONLY, None)], difficulty="hard"),
    _score("N3", [("D", CodeStatus.EXACT, 30)], difficulty="hard"),
]


def test_recall_at_k_and_mrr_are_over_expected_code_positions():
    r = RunAggregator().aggregate([], [], SCORES).retrieval

    assert r.expected_positions == 4
    assert r.recall_at == {5: 0.25, 10: 0.25, 20: 0.5, 40: 0.75}
    assert r.exact_recall == 0.75
    assert round(r.mrr, 4) == round((1 + 1 / 15 + 1 / 30) / 4, 4)
    assert r.status_counts["family_only"] == 1


def test_metrics_are_also_broken_down_by_difficulty():
    by_difficulty = RunAggregator().aggregate([], [], SCORES).retrieval_by_difficulty

    assert set(by_difficulty) == {"easy", "hard"}
    assert by_difficulty["hard"].expected_positions == 2
    assert by_difficulty["easy"].exact_recall == 1.0


def test_calls_are_grouped_by_stage_purpose_model_and_cache():
    retrievals = [
        retrieval_record("N1", [], calls=[call(input_tokens=100, latency_ms=10)]),
        retrieval_record("N2", [], calls=[call(input_tokens=300, latency_ms=30), call(input_tokens=50, cached=True, latency_ms=1)]),
    ]

    groups = {(g.stage, g.cached): g for g in RunAggregator().aggregate([], retrievals, []).calls}

    live = groups[("retrieval", False)]
    assert (live.calls, live.input_tokens, live.mean_input_tokens) == (2, 400, 200)
    assert (live.latency_ms.p50, live.latency_ms.max) == (10, 30)
    assert groups[("retrieval", True)].calls == 1


def test_failed_calls_count_but_add_no_tokens():
    retrievals = [retrieval_record("N1", [], calls=[call(input_tokens=None, error="boom"), call(input_tokens=10)])]

    [group] = RunAggregator().aggregate([], retrievals, []).calls

    assert (group.calls, group.errors, group.input_tokens) == (2, 1, 10)


def test_summary_check_rates_skip_not_applicable_checks():
    def record(pid, passed):
        return SummaryRecord(
            patient_id=pid,
            totals=StageTotals.from_calls([], 1.0),
            result=None if passed == "error" else _summary_result(),
            checks=[] if passed == "error" else [SummaryCheck(name="date", passed=passed)],
        )

    summary = RunAggregator().aggregate([record("A", True), record("B", None), record("C", False), record("D", "error")], [], []).summary

    assert summary.errors == 1
    assert (summary.checks["date"].passed, summary.checks["date"].applicable) == (1, 2)


def _summary_result():
    from app.summary import ConsultationSummaryResult
    from tests.test_consultation_summary import MOCK_RESULT

    return ConsultationSummaryResult.model_validate(MOCK_RESULT)


def test_latency_percentiles_use_nearest_rank():
    stats = LatencyStats.of([float(v) for v in range(1, 101)])

    assert (stats.p50, stats.p95, stats.max) == (50.0, 95.0, 100.0)


# -- comparison ----------------------------------------------------------------------------


def test_comparison_lists_regressions_first_and_classifies_each_note():
    baseline = [
        _score("N1", [("A", CodeStatus.EXACT, 1)]),
        _score("N2", [("B", CodeStatus.NOT_RETRIEVED, None)]),
        _score("N3", [("C", CodeStatus.EXACT, 3), ("D", CodeStatus.EXACT, 9)]),
        _score("N4", [("E", CodeStatus.EXACT, 2)]),
    ]
    candidate = [
        _score("N1", [("A", CodeStatus.EXACT, 1)]),
        _score("N2", [("B", CodeStatus.EXACT, 4)]),
        _score("N3", [("C", CodeStatus.EXACT, 1), ("D", CodeStatus.FAMILY_ONLY, None)]),
        _score("N4", [("E", CodeStatus.NOT_RETRIEVED, None)]),
    ]

    comparison = RunComparator().compare("base", baseline, "new", candidate)

    assert [(n.patient_id, n.verdict) for n in comparison.notes] == [
        ("N4", "regressed"),
        ("N3", "mixed"),
        ("N2", "improved"),
        ("N1", "unchanged"),
    ]
    assert comparison.counts == {"regressed": 1, "mixed": 1, "improved": 1, "unchanged": 1}


def test_a_family_only_hit_is_better_than_no_hit_but_worse_than_an_exact_one():
    base = [_score("N1", [("A", CodeStatus.NOT_RETRIEVED, None)]), _score("N2", [("B", CodeStatus.EXACT, 40)])]
    new = [_score("N1", [("A", CodeStatus.FAMILY_ONLY, None)]), _score("N2", [("B", CodeStatus.FAMILY_ONLY, None)])]

    verdicts = {n.patient_id: n.verdict for n in RunComparator().compare("b", base, "n", new).notes}

    assert verdicts == {"N1": "improved", "N2": "regressed"}


def test_the_report_renders_every_section():
    metrics = RunAggregator().aggregate([], [retrieval_record("N1", [], calls=[call()])], SCORES)
    comparison = RunComparator().compare("base", SCORES, "run", SCORES[:1] + [_score("N2", [("C", CodeStatus.EXACT, 2)], difficulty="hard")])

    text = MarkdownReport().render(manifest("run"), metrics, SCORES, comparison)

    for heading in ("# Benchmark run `run`", "## Retrieval", "## Cost and latency", "## Compared with `base`", "## Per note"):
        assert heading in text
    assert "C: family_only → #2" in text
