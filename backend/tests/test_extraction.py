"""Exercises the full pipeline (prompt building -> schema -> parsing -> storage -> API)
against a mocked model response, since no live Mistral API call is made in this
environment. Once MISTRAL_API_KEY is configured, see scripts/try_extraction.py for a
live smoke test.

Uses the small tests/fixtures/reference_data_test.json table (via the small_reference_table
fixture in conftest.py) rather than the real llama_index vector store, so these tests don't
depend on its size, network access, or exact content."""

import itertools
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
        },
        {
            "code": "TEST-BLOODWORK-ORDER",
            "description": "Demande et révision d'un bilan sanguin de routine",
            "confidence": "medium",
            "explanation": "Bilan sanguin de contrôle demandé",
            "supporting_quote": "Bilan sanguin de contrôle demandé",
            "needs_confirmation": [],
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


def _extract(client: TestClient, *, patient_id: int, summary=MOCK_SUMMARY_RESULT, billing=MOCK_RESULT):
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.achat = AsyncMock(
            side_effect=[_mock_response(summary), _mock_response(billing)]
        )
        return client.post(
            "/extract",
            json={
                "transcript": SAMPLE_TRANSCRIPT,
                "task": "billing_codes",
                "patient_id": patient_id,
                "source": {"system": "plume_ai", "encounter_id": "enc-123"},
            },
        )


# Patients are globally unique by NAM now, and the test DB is shared across the whole
# session (see conftest.py) — a default of None generates a fresh NAM per call so tests
# that don't care about the exact value never collide with each other.
_ramq_numbers = itertools.count(1)


async def _seed_patient(*, ramq_number=None, full_name="Louise Tremblay"):
    return await PatientRepository().create(
        full_name=full_name,
        ramq_number=ramq_number or f"EXTR{next(_ramq_numbers):08d}",
        date_of_birth=date(1958, 2, 15),
        gender=Gender.FEMALE,
        is_vulnerable=False,
    )


async def test_extract_endpoint_end_to_end():
    # Using TestClient as a context manager triggers the FastAPI lifespan (init_db()).
    # billing_codes is now a two-stage pipeline (consultation_summary, then billing_codes
    # off that summary) — two chat-completion calls happen, so mock two responses in order.
    with TestClient(app) as client:
        patient = await _seed_patient()
        response = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    body = response.json()
    assert body["billing"]["task"] == "billing_codes"
    assert len(body["billing"]["result"]["codes"]) == 2
    assert isinstance(body["summary_extraction_record_id"], int)
    assert isinstance(body["billing_extraction_record_id"], int)
    # MOCK_SUMMARY_RESULT's encounter_setting.date is null -> must stay null, never "today".
    assert body["encounter_date"] is None
    assert body["encounter_date_raw"] is None


async def test_extract_endpoint_resolves_fees_from_the_real_candidate_data():
    # The mocked model response above carries no fee data at all (the model is never asked
    # for one — see app/ramq_codes/models.py's ExtractedCode.fees server_only marker); fees
    # must come from the pipeline's post-extraction resolution step
    # (BillingCodesTask.resolve_fees) reading the real fixture data
    # (tests/fixtures/reference_data_test.json), not from the mock.
    with TestClient(app) as client:
        patient = await _seed_patient()
        response = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    codes = {c["code"]: c for c in response.json()["billing"]["result"]["codes"]}
    assert codes["TEST-BP-MGMT"]["fees"] == [
        {"amount": 33.15, "amount_text": "33,15", "context": "Par visite de suivi", "lieu": None, "majoration": None}
    ]
    assert codes["TEST-BLOODWORK-ORDER"]["fees"] == []


async def test_extract_endpoint_requires_a_known_patient_id():
    with TestClient(app) as client:
        response = _extract(client, patient_id=999999)

    assert response.status_code == 404


async def test_extract_endpoint_reports_no_mismatch_when_transcript_agrees_with_the_chosen_patient():
    with TestClient(app) as client:
        patient = await _seed_patient(ramq_number="TREL58021501", full_name="Louise Tremblay")
        response = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    verification = response.json()["patient_verification"]
    assert verification["nam_mismatch"] is False
    assert verification["name_mismatch"] is False
    assert verification["extracted"]["name_as_stated"] == "Tremblay, Louise"


async def test_extract_endpoint_reports_nam_mismatch_when_transcript_disagrees():
    with TestClient(app) as client:
        # Chosen patient's NAM differs from what the (mocked) transcript extraction states.
        patient = await _seed_patient(ramq_number="AUTR00000000", full_name="Quelqu'un Dautre")
        response = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    verification = response.json()["patient_verification"]
    assert verification["nam_mismatch"] is True
    assert verification["name_mismatch"] is True


async def test_extract_endpoint_no_nam_in_transcript_leaves_nam_mismatch_unknown():
    summary_without_nam = {
        **MOCK_SUMMARY_RESULT,
        "patient_information": {**MOCK_SUMMARY_RESULT["patient_information"], "ramq_number_as_stated": None},
    }

    with TestClient(app) as client:
        patient = await _seed_patient()
        response = _extract(client, patient_id=patient.id, summary=summary_without_nam)

    assert response.status_code == 200
    verification = response.json()["patient_verification"]
    assert verification["nam_mismatch"] is None
    assert verification["extracted"]["name_as_stated"] == "Tremblay, Louise"


def test_unknown_task_returns_400():
    with TestClient(app) as client:
        response = client.post(
            "/extract", json={"transcript": "hello", "task": "not_a_real_task", "patient_id": 1}
        )
    assert response.status_code == 400
