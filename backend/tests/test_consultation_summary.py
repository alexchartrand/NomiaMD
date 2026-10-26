"""Exercises the consultation_summary step (ConsultationSummarizer) against a mocked model
response — same pattern as test_code_selector.py's billing_codes tests."""

from unittest.mock import AsyncMock, patch

from app.summary import ConsultationSummarizer, ConsultationSummaryResult, render_for_billing_codes
from tests.llm_helpers import fake_chat_result

SAMPLE_TRANSCRIPT = (
    "Patiente de 58 ans suivie pour diabète de type 2 depuis 6 ans et hypertension "
    "artérielle depuis 10 ans, se présente en cabinet sur rendez-vous pour son suivi "
    "trimestriel. Patiente inscrite. Tension artérielle mesurée à 138/86. HbA1c à "
    "7,8 %, cible non atteinte. Ajustement de la médication antihypertensive envisagé. "
    "Bilan sanguin de contrôle demandé (HbA1c, fonction rénale, ions) dans 3 mois pour "
    "réévaluer le contrôle glycémique."
)

MOCK_RESULT = {
    "short_description": "Suivi trimestriel de diabète de type 2 et d'hypertension artérielle, ajustement de la médication envisagé.",
    "encounter_setting": {
        "location_detail": None,
        "date": None,
        "time_start": None,
        "time_end": None,
        "duration_minutes": 15,
        "duration_explicitly_stated": False,
        "appointment_type": "avec rendez-vous",
    },
    "pregnancy_context": {"present": False, "trimester": None},
    "referral_information": {
        "present": False,
        "requester_role": None,
        "requester_identifier_mentioned": None,
        "reason_for_referral": None,
        "written_report_back_required_or_produced": None,
    },
    "clinical_summary": {
        "chief_complaint_or_reason_for_visit": "Suivi trimestriel de diabète de type 2 et d'hypertension artérielle",
        "systems_or_body_regions_involved": ["endocrinien", "cardiovasculaire"],
        "single_vs_multi_system": "multi",
        "history_taken": True,
        "new_treatment_initiated": False,
        "existing_treatment_reviewed_or_adjusted": True,
        "diagnosis_or_impression_stated": "Diabète de type 2 et hypertension artérielle, contrôle glycémique sous-optimal",
        "recommendations_given_to_patient": True,
        "orders_or_prescriptions_mentioned": True,
    },
    "physical_examination": {
        "performed": True,
        "regions_or_systems_examined": ["tension artérielle"],
        "notable_findings": "Tension artérielle mesurée à 138/86",
    },
    "procedures_performed": [],
    "possible_billable_add_ons": [],
    "notes_uncertain_items": [],
}


def _mock_response():
    return fake_chat_result(MOCK_RESULT)


async def test_summarize_parses_mocked_response():
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(return_value=_mock_response())
        summarized = await ConsultationSummarizer().summarize(SAMPLE_TRANSCRIPT)

    assert summarized.summary.clinical_summary.single_vs_multi_system == "multi"
    assert summarized.summary.clinical_summary.systems_or_body_regions_involved == [
        "endocrinien",
        "cardiovasculaire",
    ]
    assert summarized.model == mock_get_client.return_value.chat.return_value.model
    messages = mock_get_client.return_value.chat.call_args.kwargs["messages"]
    assert SAMPLE_TRANSCRIPT in messages[1].content


def test_render_for_billing_codes_surfaces_quotable_facts():
    # billing_codes.py's explanation requirement depends on this rendering actually
    # containing the underlying facts verbatim, not just describing that they exist.
    summary = ConsultationSummaryResult.model_validate(MOCK_RESULT)
    rendered = render_for_billing_codes(summary)

    assert MOCK_RESULT["short_description"] in rendered
    assert MOCK_RESULT["clinical_summary"]["chief_complaint_or_reason_for_visit"] in rendered
    assert MOCK_RESULT["physical_examination"]["notable_findings"] in rendered
    # Null/empty fields (no referral, no procedures, no notes here) must not leak in as
    # literal "None"/"null" text — a missing line is how absence is represented.
    assert "None" not in rendered
    assert "null" not in rendered


def test_render_for_billing_codes_includes_procedure_and_pregnancy_lines():
    data = {
        **MOCK_RESULT,
        "pregnancy_context": {"present": True, "trimester": "deuxième"},
        "procedures_performed": [
            {
                "procedure_description": "Suture d'une plaie de 3 cm",
                "body_site": "avant-bras gauche",
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "local",
                "diagnostic_or_therapeutic": "thérapeutique",
            }
        ],
    }
    rendered = render_for_billing_codes(ConsultationSummaryResult.model_validate(data))

    assert "Grossesse" in rendered and "deuxième" in rendered
    assert "Suture d'une plaie de 3 cm" in rendered
    assert "avant-bras gauche" in rendered
