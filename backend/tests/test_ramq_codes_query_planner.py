"""Unit tests for SummaryQueryPlanner and TranscriptQueryPlanner
(app/ramq_codes/query_planner.py) — pure data transformation, no LLM, no DB."""

from app.ramq_codes.query_planner import PlannedQuery, SummaryQueryPlanner, TranscriptQueryPlanner
from app.summary import ConsultationSummaryResult, render_for_billing_codes
from tests.test_consultation_summary import MOCK_RESULT


def _summary(**overrides) -> ConsultationSummaryResult:
    return ConsultationSummaryResult.model_validate({**MOCK_RESULT, **overrides})


def test_a_visit_with_no_procedures_or_add_ons_yields_a_single_query():
    summary = _summary()

    queries = SummaryQueryPlanner().plan(summary)

    assert queries == [render_for_billing_codes(summary)]


def test_each_procedure_becomes_its_own_query():
    summary = _summary(
        procedures_performed=[
            {
                "procedure_description": "Suture d'une lacération de 3cm",
                "body_site": None,
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "local",
                "diagnostic_or_therapeutic": "thérapeutique",
            },
            {
                "procedure_description": "ECG réalisé et interprété",
                "body_site": None,
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "aucun",
                "diagnostic_or_therapeutic": "diagnostique",
            },
        ]
    )

    queries = SummaryQueryPlanner().plan(summary)

    assert queries[1:] == ["Suture d'une lacération de 3cm", "ECG réalisé et interprété"]
    assert len(queries) == 3  # the base summary query plus one per procedure


def test_each_possible_add_on_becomes_its_own_query():
    summary = _summary(possible_billable_add_ons=["deplacement_urgence", "frais_kilometrage"])

    queries = SummaryQueryPlanner().plan(summary)

    assert queries[1:] == ["deplacement_urgence", "frais_kilometrage"]


def test_the_base_query_is_always_first():
    summary = _summary(possible_billable_add_ons=["deplacement_urgence"])

    queries = SummaryQueryPlanner().plan(summary)

    assert queries[0] == render_for_billing_codes(summary)


def test_labeled_queries_name_where_each_query_came_from():
    summary = _summary(
        procedures_performed=[
            {
                "procedure_description": "ECG réalisé et interprété",
                "body_site": None,
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "aucun",
                "diagnostic_or_therapeutic": "diagnostique",
            }
        ],
        possible_billable_add_ons=["frais_kilometrage"],
    )

    queries = SummaryQueryPlanner().plan_labeled(summary)

    assert [q.source for q in queries] == ["visit", "procedure", "add_on"]
    assert [q.text for q in queries] == SummaryQueryPlanner().plan(summary)


def test_the_transcript_planner_makes_one_query_with_the_nam_redacted():
    transcript = "**NAM :** TREM 5802 1518\nSuivi de diabète."

    [query] = TranscriptQueryPlanner().plan(transcript)

    assert query == PlannedQuery(text="**NAM :** [NAM]\nSuivi de diabète.", source="transcript")
