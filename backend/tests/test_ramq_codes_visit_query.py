"""Unit tests for VisitQueryRenderer (app/ramq_codes/visit_query.py): the visit query says
what kind of encounter it was, and never what it was about."""

import copy

from app.ramq_codes.visit_query import VisitQueryRenderer
from app.summary import ConsultationSummaryResult
from tests.test_consultation_summary import MOCK_RESULT


def _render(**section_overrides) -> str:
    data = copy.deepcopy(MOCK_RESULT)
    for section, fields in section_overrides.items():
        data[section].update(fields)
    return VisitQueryRenderer().render(ConsultationSummaryResult.model_validate(data))


def test_a_plain_visit_renders_its_appointment_type_and_systems():
    assert _render() == "Visite. avec rendez-vous. Plusieurs systèmes"


def test_no_clinical_content_leaks_into_the_query():
    query = _render()

    for clinical in ("diabète", "hypertension", "Tension artérielle", "endocrinien", "Suivi trimestriel"):
        assert clinical not in query


def test_the_location_is_kept_verbatim():
    query = _render(encounter_setting={"location_detail": "Unité de médecine 4e Nord (courte durée)"})

    assert "Unité de médecine 4e Nord (courte durée)" in query


def test_a_referral_is_rendered_in_the_manuals_own_opinion_visit_wording():
    query = _render(referral_information={"present": True, "requester_role": "medecin_omnipraticien"})

    assert query.startswith("Visite d'évaluation pour donner une opinion. ")
    assert "omnipraticien" not in query


def test_pregnancy_names_the_trimester_only_when_known():
    assert "Grossesse, premier trimestre" in _render(pregnancy_context={"present": True, "trimester": "premier"})
    assert "Grossesse." in _render(pregnancy_context={"present": True, "trimester": "incertain"})


def test_only_an_explicitly_stated_duration_is_rendered():
    assert "Durée" not in _render()  # the fixture's 15 minutes are estimated
    assert "Durée 45 minutes" in _render(encounter_setting={"duration_minutes": 45, "duration_explicitly_stated": True})


def test_missing_facts_are_skipped():
    query = _render(
        encounter_setting={"appointment_type": None},
        clinical_summary={"single_vs_multi_system": "incertain"},
    )

    assert query == "Visite"
