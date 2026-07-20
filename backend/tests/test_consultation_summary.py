"""Exercises the consultation_summary task against a mocked model response — same pattern
as test_extraction.py's billing_codes tests."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.extraction.engine import run_extraction
from app.main import app
from app.models import ConsultationSummaryResult
from app.tasks.consultation_summary import render_for_billing_codes
from app.tasks.registry import get_task

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
        "location_type": "cabinet",
        "location_detail": None,
        "date": None,
        "time_start": None,
        "time_end": None,
        "duration_minutes": 15,
        "duration_explicitly_stated": False,
        "appointment_type": "sur_rendez_vous",
    },
    "patient_information": {
        "age_years": 58,
        "age_months_if_infant": None,
        "sex_if_stated": None,
        "pregnancy_context": {"present": False, "trimester": None},
        "relevant_vulnerability_or_context_mentioned": [],
        "new_or_established_patient_language": "Patiente inscrite",
    },
    "referral_information": {
        "present": False,
        "referral_type": "aucune",
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
        "special_exam_type": [],
        "notable_findings": "Tension artérielle mesurée à 138/86",
    },
    "procedures_performed": [],
    "encounter_category_hint": {
        "best_guess_category": "visite_suivi_ou_prise_en_charge",
        "confidence": "high",
        "rationale": "Suivi trimestriel documenté d'un patient déjà pris en charge pour diabète et hypertension.",
    },
    "possible_billable_add_ons": [],
    "notes_uncertain_items": [],
}


def _mock_response():
    return SimpleNamespace(
        model="local-model",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps(MOCK_RESULT)),
            )
        ],
    )


def test_run_extraction_parses_mocked_response():
    task = get_task("consultation_summary")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = _mock_response()
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert result.task == "consultation_summary"
    assert result.result.encounter_category_hint.best_guess_category == "visite_suivi_ou_prise_en_charge"
    assert result.result.encounter_category_hint.confidence == "high"
    assert result.result.clinical_summary.single_vs_multi_system == "multi"
    assert result.result.clinical_summary.systems_or_body_regions_involved == [
        "endocrinien",
        "cardiovasculaire",
    ]


def test_extract_endpoint_end_to_end():
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = _mock_response()
        with TestClient(app) as client:
            response = client.post(
                "/extract",
                json={"transcript": SAMPLE_TRANSCRIPT, "task": "consultation_summary"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "consultation_summary"
    assert body["result"]["encounter_category_hint"]["best_guess_category"] == "visite_suivi_ou_prise_en_charge"
    assert body["result"]["referral_information"]["present"] is False


def test_render_for_billing_codes_surfaces_quotable_facts():
    # billing_codes.py's supporting_quote requirement depends on this rendering actually
    # containing the underlying facts verbatim, not just describing that they exist.
    summary = ConsultationSummaryResult.model_validate(MOCK_RESULT)
    rendered = render_for_billing_codes(summary)

    assert MOCK_RESULT["short_description"] in rendered
    assert MOCK_RESULT["clinical_summary"]["chief_complaint_or_reason_for_visit"] in rendered
    assert MOCK_RESULT["physical_examination"]["notable_findings"] in rendered
    assert MOCK_RESULT["patient_information"]["new_or_established_patient_language"] in rendered
    # Null/empty fields (no referral, no procedures, no notes here) must not leak in as
    # literal "None"/"null" text — a missing line is how absence is represented.
    assert "None" not in rendered
    assert "null" not in rendered


def test_render_for_billing_codes_includes_procedure_and_pregnancy_lines():
    data = {
        **MOCK_RESULT,
        "patient_information": {
            **MOCK_RESULT["patient_information"],
            "pregnancy_context": {"present": True, "trimester": "beyond_first"},
        },
        "procedures_performed": [
            {
                "procedure_description": "Suture d'une plaie de 3 cm",
                "body_site": "avant-bras gauche",
                "technique_or_approach_mentioned": None,
                "anesthesia_used": "local",
                "diagnostic_or_therapeutic": "therapeutique",
            }
        ],
    }
    rendered = render_for_billing_codes(ConsultationSummaryResult.model_validate(data))

    assert "Grossesse" in rendered and "beyond_first" in rendered
    assert "Suture d'une plaie de 3 cm" in rendered
    assert "avant-bras gauche" in rendered
