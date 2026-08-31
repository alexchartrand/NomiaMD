"""Exercises the full pipeline (prompt building -> schema -> parsing -> storage -> API)
against a mocked model response, since no live Mistral API call is made in this
environment. Once MISTRAL_API_KEY is configured, see scripts/try_extraction.py for a
live smoke test.

Uses the small tests/fixtures/reference_data_test.json table (via the small_reference_table
fixture in conftest.py) rather than the real llama_index vector store, so these tests don't
depend on its size, network access, or exact content."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.extraction.engine import run_extraction
from app.main import app
from app.postgresdb import Gender, PatientRepository
from app.ramq_codes import BillingCodesInput, BillingContext
from app.summary import ConsultationSummaryResult
from app.tasks.registry import get_task

# default_authenticated_user (conftest.py, autouse) injects a fake physician with this id.
PHYSICIAN_ID = 1

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
        "sex_if_stated": "F",
        "name_as_stated": "Tremblay, Louise",
        "ramq_number_as_stated": "TREL58021501",
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
    "notes_uncertain_items": ["Bilan sanguin de contrôle demandé (HbA1c, fonction rénale) dans 3 mois"],
}

MOCK_RESULT = {
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une maladie chronique, hypertension artérielle",
            "confidence": "high",
            "explanation": "hypertension artérielle depuis 10 ans",
            "supporting_quote": "hypertension artérielle depuis 10 ans",
            "needs_confirmation": [],
            "fee": {"amount": 33.15, "when_to_use": "Par visite de suivi", "majoration": None},
        },
        {
            "code": "TEST-BLOODWORK-ORDER",
            "description": "Demande et révision d'un bilan sanguin de routine",
            "confidence": "medium",
            "explanation": "Bilan sanguin de contrôle demandé",
            "supporting_quote": "Bilan sanguin de contrôle demandé",
            "needs_confirmation": [],
            "fee": {"amount": None, "when_to_use": None, "majoration": None},
        },
    ],
    "notes": None,
}


def _billing_codes_input() -> BillingCodesInput:
    # run_extraction(task, task_input) now takes BillingCodesTask's own input bundle
    # (see app/ramq_codes/task.py's BillingCodesInput) rather than a bare transcript string
    # — the retriever needs the structured summary to plan retrieval queries from, and the
    # rendered text of MOCK_SUMMARY_RESULT is what the small_reference_table stub retriever
    # (conftest.py) keyword-matches against.
    return BillingCodesInput(
        summary=ConsultationSummaryResult.model_validate(MOCK_SUMMARY_RESULT),
        transcript=SAMPLE_TRANSCRIPT,
        context=BillingContext(),
    )


def _mock_response(payload=MOCK_RESULT):
    return SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(payload)),
        raw={
            "model": "mistral-small-latest",
            "choices": [SimpleNamespace(finish_reason="stop")],
        },
    )


async def test_run_extraction_parses_mocked_response():
    task = get_task("billing_codes")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.achat = AsyncMock(return_value=_mock_response())
        result = await run_extraction(task, _billing_codes_input())

    assert result.task == "billing_codes"
    assert [c.code for c in result.result.codes] == [
        "TEST-BP-MGMT",
        "TEST-BLOODWORK-ORDER",
    ]
    # The prompt actually sent to the model should have narrowed candidates via keyword
    # match, not dumped the whole reference table — confirm the call args reflect that.
    call_kwargs = mock_get_client.return_value.achat.call_args.kwargs
    user_message = call_kwargs["messages"][1].content
    assert "TEST-BP-MGMT" in user_message
    assert "TEST-CONSULT-NEW" not in user_message  # not relevant to this transcript


async def test_run_extraction_drops_malformed_bare_string_codes():
    """A small local model sometimes collapses the codes array to bare code strings
    instead of {code, description, confidence, explanation} objects, especially with
    a large real candidate list — this must not crash the request, and must not fabricate
    an explanation for something the model didn't actually justify."""
    task = get_task("billing_codes")
    mock_result = {
        "codes": [
            "TEST-BP-MGMT",
            {
                "code": "TEST-BLOODWORK-ORDER",
                "description": "Demande et révision d'un bilan sanguin de routine",
                "confidence": "medium",
                "explanation": "Bilan sanguin de contrôle demandé",
                "supporting_quote": "Bilan sanguin de contrôle demandé",
                "needs_confirmation": [],
                "fee": {"amount": None, "when_to_use": None, "majoration": None},
            },
        ],
        "notes": None,
    }
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.achat = AsyncMock(return_value=_mock_response(mock_result))
        result = await run_extraction(task, _billing_codes_input())

    assert [c.code for c in result.result.codes] == ["TEST-BLOODWORK-ORDER"]
    assert result.result.notes is not None
    assert "1 candidate code" in result.result.notes


def _extract(client: TestClient, *, summary=MOCK_SUMMARY_RESULT, billing=MOCK_RESULT):
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.achat = AsyncMock(
            side_effect=[_mock_response(summary), _mock_response(billing)]
        )
        return client.post(
            "/extract",
            json={
                "transcript": SAMPLE_TRANSCRIPT,
                "task": "billing_codes",
                "source": {"system": "plume_ai", "encounter_id": "enc-123"},
            },
        )


def test_extract_endpoint_end_to_end():
    # Using TestClient as a context manager triggers the FastAPI lifespan (init_db()).
    # billing_codes is now a two-stage pipeline (consultation_summary, then billing_codes
    # off that summary) — two chat-completion calls happen, so mock two responses in order.
    with TestClient(app) as client:
        response = _extract(client)

    assert response.status_code == 200
    body = response.json()
    assert body["billing"]["task"] == "billing_codes"
    assert len(body["billing"]["result"]["codes"]) == 2
    assert isinstance(body["summary_extraction_record_id"], int)
    assert isinstance(body["billing_extraction_record_id"], int)
    # MOCK_SUMMARY_RESULT's encounter_setting.date is null -> must stay null, never "today".
    assert body["encounter_date"] is None
    assert body["encounter_date_raw"] is None


async def test_extract_endpoint_matches_roster_patient_by_nam():
    with TestClient(app) as client:
        # Entering the TestClient context triggers the lifespan's init_db() first, so the
        # patients table is guaranteed to exist before this direct repository seed.
        patient = await PatientRepository().create(
            physician_id=PHYSICIAN_ID,
            full_name="Louise Tremblay",
            ramq_number="TREL58021501",
            date_of_birth=date(1958, 2, 15),
            gender=Gender.FEMALE,
            is_registered_with_physician=True,
            is_vulnerable=False,
        )
        response = _extract(client)

    assert response.status_code == 200
    suggestion = response.json()["patient_suggestion"]
    assert suggestion["matched_patient_id"] == patient.id
    assert suggestion["extracted"]["name_as_stated"] == "Tremblay, Louise"


async def test_extract_endpoint_no_nam_in_note_no_match_but_extracted_present():
    summary_without_nam = {
        **MOCK_SUMMARY_RESULT,
        "patient_information": {**MOCK_SUMMARY_RESULT["patient_information"], "ramq_number_as_stated": None},
    }

    with TestClient(app) as client:
        response = _extract(client, summary=summary_without_nam)

    assert response.status_code == 200
    suggestion = response.json()["patient_suggestion"]
    assert suggestion["matched_patient_id"] is None
    assert suggestion["extracted"]["name_as_stated"] == "Tremblay, Louise"
    assert suggestion["extracted"]["suggested_full_name"] == "Louise Tremblay"


def test_unknown_task_returns_400():
    with TestClient(app) as client:
        response = client.post(
            "/extract", json={"transcript": "hello", "task": "not_a_real_task"}
        )
    assert response.status_code == 400
