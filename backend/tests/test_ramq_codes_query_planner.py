"""Unit tests for SummaryQueryPlanner and TranscriptQueryPlanner
(app/ramq_codes/query_planner.py) — pure data transformation, no LLM, no DB."""

from app.care_setting import CareSetting
from app.ramq_codes.query_planner import PlannedQuery, SummaryQueryPlanner, TranscriptQueryPlanner
from app.ramq_codes.visit_query import CARE_SETTING_VISIT_SECTIONS, VISIT_SECTION_PREFIX, VisitQueryRenderer
from app.summary import ConsultationSummaryResult, render_for_billing_codes
from tests.test_consultation_summary import MOCK_RESULT


def _summary(**overrides) -> ConsultationSummaryResult:
    return ConsultationSummaryResult.model_validate({**MOCK_RESULT, **overrides})


def test_a_visit_with_no_procedures_or_add_ons_yields_the_visit_and_overview_queries():
    summary = _summary()

    queries = SummaryQueryPlanner().plan(summary)

    assert queries == [VisitQueryRenderer().render(summary), render_for_billing_codes(summary)]


def test_only_the_visit_query_is_scoped_to_the_visit_section():
    summary = _summary(possible_billable_add_ons=["frais_kilometrage"])

    queries = SummaryQueryPlanner().plan_labeled(summary)

    assert [(q.source, q.section_prefixes) for q in queries] == [
        ("visit", (VISIT_SECTION_PREFIX,)),
        ("overview", None),
        ("add_on", None),
    ]


def test_an_er_encounter_also_searches_the_er_subsection_with_the_same_visit_query():
    summary = _summary()

    queries = SummaryQueryPlanner().plan_labeled(summary, CareSetting.URGENCE)

    visit = VisitQueryRenderer().render(summary)
    assert queries[:3] == [
        PlannedQuery(visit, "visit", section_prefixes=(VISIT_SECTION_PREFIX,)),
        PlannedQuery(visit, "care_setting_visit", section_prefixes=(CARE_SETTING_VISIT_SECTIONS[CareSetting.URGENCE],)),
        PlannedQuery(render_for_billing_codes(summary), "overview"),
    ]
    assert CARE_SETTING_VISIT_SECTIONS[CareSetting.URGENCE].startswith(f"{VISIT_SECTION_PREFIX} > ")


def test_a_setting_without_its_own_subsection_or_none_plans_as_before():
    summary = _summary()

    assert SummaryQueryPlanner().plan_labeled(summary, CareSetting.CABINET) == SummaryQueryPlanner().plan_labeled(summary)
    assert [q.source for q in SummaryQueryPlanner().plan_labeled(summary, None)] == ["visit", "overview"]


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

    assert queries[2:] == ["Suture d'une lacération de 3cm", "ECG réalisé et interprété"]
    assert len(queries) == 4  # the visit and overview queries plus one per procedure


def test_a_procedure_with_a_generic_name_searches_it_and_its_detailed_wording_separately():
    summary = _summary(
        procedures_performed=[
            {
                "procedure_description": "Suture d'une lacération de 3cm à l'avant-bras gauche",
                "generic_act": "réparation de lacération simple",
                "body_site": "avant-bras gauche",
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "local",
                "diagnostic_or_therapeutic": "thérapeutique",
            }
        ]
    )

    queries = SummaryQueryPlanner().plan_labeled(summary)

    assert [(q.source, q.text) for q in queries[2:]] == [
        ("procedure", "réparation de lacération simple"),
        ("procedure_detail", "Suture d'une lacération de 3cm à l'avant-bras gauche"),
    ]


def test_each_possible_add_on_becomes_its_own_query():
    summary = _summary(possible_billable_add_ons=["deplacement_urgence", "frais_kilometrage"])

    queries = SummaryQueryPlanner().plan(summary)

    assert queries[2:] == ["deplacement_urgence", "frais_kilometrage"]


def test_the_overview_query_is_the_full_rendered_summary():
    summary = _summary(possible_billable_add_ons=["deplacement_urgence"])

    queries = SummaryQueryPlanner().plan(summary)

    assert queries[1] == render_for_billing_codes(summary)


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

    assert [q.source for q in queries] == ["visit", "overview", "procedure", "add_on"]
    assert [q.text for q in queries] == SummaryQueryPlanner().plan(summary)


def test_the_transcript_planner_makes_one_query_with_the_nam_redacted():
    transcript = "**NAM :** TREM 5802 1518\nSuivi de diabète."

    [query] = TranscriptQueryPlanner().plan(transcript)

    assert query == PlannedQuery(text="**NAM :** [NAM]\nSuivi de diabète.", source="transcript")
