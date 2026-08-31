"""Unit tests for SummaryQueryPlanner (app/ramq_codes/query_planner.py) — pure data
transformation off ConsultationSummaryResult's own fields, no LLM, no DB."""

from app.ramq_codes.query_planner import SummaryQueryPlanner
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
                "diagnostic_or_therapeutic": "therapeutique",
            },
            {
                "procedure_description": "ECG réalisé et interprété",
                "body_site": None,
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "none",
                "diagnostic_or_therapeutic": "diagnostic",
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
