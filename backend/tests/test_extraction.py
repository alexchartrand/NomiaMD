"""Exercises the full pipeline (prompt building -> schema -> parsing -> storage -> API)
against a mocked model response, since no local model server is available in this
environment. Once NOMIAMD_BASE_URL is configured, see scripts/try_extraction.py for a
live smoke test.

Uses the small tests/fixtures/reference_data_test.json table (via the small_reference_table
fixture in conftest.py) rather than the real reference_data.json, so these tests don't
depend on its size or exact content."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.extraction.engine import run_extraction
from app.main import app
from app.tasks.registry import get_task

SAMPLE_TRANSCRIPT = (
    "Patiente de 58 ans suivie pour diabète de type 2 depuis 6 ans et hypertension "
    "artérielle depuis 10 ans, se présente pour son suivi trimestriel. Tension artérielle "
    "mesurée à 138/86. HbA1c à 7,8 %, cible non atteinte. Ajustement de la médication "
    "antihypertensive envisagé. Bilan sanguin de contrôle demandé (HbA1c, fonction rénale, "
    "ions) dans 3 mois pour réévaluer le contrôle glycémique."
)

MOCK_SUMMARY_RESULT = {
    "short_description": "Suivi trimestriel de diabète de type 2 et d'hypertension artérielle.",
    "encounter_setting": {
        "location_type": "cabinet",
        "location_detail": None,
        "date": None,
        "time_start": None,
        "time_end": None,
        "duration_minutes": None,
        "duration_explicitly_stated": False,
        "appointment_type": "inconnu",
    },
    "patient_information": {
        "age_years": 58,
        "age_months_if_infant": None,
        "sex_if_stated": None,
        "pregnancy_context": {"present": False, "trimester": None},
        "relevant_vulnerability_or_context_mentioned": [],
        "new_or_established_patient_language": None,
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
        "diagnosis_or_impression_stated": "Hypertension artérielle et diabète de type 2, cible glycémique non atteinte",
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
        "rationale": "Suivi documenté d'un patient déjà pris en charge pour diabète et hypertension.",
    },
    "possible_billable_add_ons": [],
    "notes_uncertain_items": [],
}

MOCK_RESULT = {
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une maladie chronique, hypertension artérielle",
            "confidence": 0.9,
            "supporting_quote": "hypertension artérielle depuis 10 ans",
        },
        {
            "code": "TEST-BLOODWORK-ORDER",
            "description": "Demande et révision d'un bilan sanguin de routine",
            "confidence": 0.85,
            "supporting_quote": "Bilan sanguin de contrôle demandé",
        },
    ],
    "notes": None,
}


def _mock_response(payload=MOCK_RESULT):
    return SimpleNamespace(
        model="local-model",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps(payload)),
            )
        ],
    )


def test_run_extraction_parses_mocked_response():
    task = get_task("billing_codes")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = _mock_response()
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert result.task == "billing_codes"
    assert [c.code for c in result.result.codes] == [
        "TEST-BP-MGMT",
        "TEST-BLOODWORK-ORDER",
    ]
    # The prompt actually sent to the model should have narrowed candidates via keyword
    # match, not dumped the whole reference table — confirm the call args reflect that.
    call_kwargs = mock_get_client.return_value.chat.completions.create.call_args.kwargs
    user_message = call_kwargs["messages"][1]["content"]
    assert "TEST-BP-MGMT" in user_message
    assert "TEST-CONSULT-NEW" not in user_message  # not relevant to this transcript


def test_run_extraction_enriches_prices_from_reference_table():
    """Price must come from the reference table lookup, not from the (mocked) model
    output — the mock response above doesn't include price_cad at all."""
    task = get_task("billing_codes")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = _mock_response()
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    prices = {c.code: c.price_cad for c in result.result.codes}
    assert prices == {
        "TEST-BP-MGMT": 35.75,
        "TEST-BLOODWORK-ORDER": 18.25,
    }
    assert result.result.total_price_cad == 54.0


def test_run_extraction_handles_code_not_in_reference_table():
    """If the model somehow returns a code with no match (or no price on file), price
    should be None rather than the pipeline erroring or fabricating a number."""
    task = get_task("billing_codes")
    mock_result = {
        "codes": [
            {
                "code": "NOT-IN-TABLE",
                "description": "Unknown",
                "confidence": 0.5,
                "supporting_quote": "n/a",
            }
        ],
        "notes": None,
    }
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = SimpleNamespace(
            model="local-model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=json.dumps(mock_result)),
                )
            ],
        )
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert result.result.codes[0].price_cad is None
    assert result.result.total_price_cad is None


def test_run_extraction_drops_malformed_bare_string_codes():
    """A small local model sometimes collapses the codes array to bare code strings
    instead of {code, description, confidence, supporting_quote} objects, especially with
    a large real candidate list — this must not crash the request, and must not fabricate
    a supporting_quote for something the model didn't actually justify."""
    task = get_task("billing_codes")
    mock_result = {
        "codes": [
            "TEST-BP-MGMT",
            {
                "code": "TEST-BLOODWORK-ORDER",
                "description": "Demande et révision d'un bilan sanguin de routine",
                "confidence": 0.85,
                "supporting_quote": "Bilan sanguin de contrôle demandé",
            },
        ],
        "notes": None,
    }
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = SimpleNamespace(
            model="local-model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=json.dumps(mock_result)),
                )
            ],
        )
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert [c.code for c in result.result.codes] == ["TEST-BLOODWORK-ORDER"]
    assert result.result.notes is not None
    assert "1 candidate code" in result.result.notes


def test_extract_endpoint_end_to_end():
    # DATABASE_URL is bound to a SQLAlchemy engine at import time (app/db.py), so it can't
    # be swapped per-test via monkeypatch here — this exercises the real dev DB's schema.
    # Using TestClient as a context manager triggers the FastAPI lifespan (init_db()).
    # billing_codes is now a two-stage pipeline (consultation_summary, then billing_codes
    # off that summary) — two chat-completion calls happen, so mock two responses in order.
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = [
            _mock_response(MOCK_SUMMARY_RESULT),
            _mock_response(MOCK_RESULT),
        ]
        with TestClient(app) as client:
            response = client.post(
                "/extract",
                json={
                    "transcript": SAMPLE_TRANSCRIPT,
                    "task": "billing_codes",
                    "source": {"system": "plume_ai", "encounter_id": "enc-123"},
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "billing_codes"
    assert len(body["result"]["codes"]) == 2
    assert body["result"]["total_price_cad"] == 54.0


def test_unknown_task_returns_400():
    with TestClient(app) as client:
        response = client.post(
            "/extract", json={"transcript": "hello", "task": "not_a_real_task"}
        )
    assert response.status_code == 400
