"""Exercises the full pipeline (prompt building -> schema -> parsing -> storage -> API)
against a mocked model response, since no live Mistral API call is made in this
environment. Once LLM_API_KEY and EMBEDDING_API_KEY are configured, see scripts/try_extraction.py for a
live smoke test.

Uses the small tests/fixtures/reference_data_test.json table (via the small_reference_table
fixture in conftest.py) rather than the real LanceDB codes table, so these tests don't
depend on its size, network access, or exact content."""

import itertools
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.intake import content_hash
from app.llm import ExtractionOutputError
from app.main import app
from app.postgresdb import Encounter, ExtractionRun, ExtractionRunResult, Gender, PatientRepository, session_scope
from app.summary import ConsultationSummarizer
from tests.llm_helpers import fake_chat_result

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
        "location_detail": None,
        "date": None,
        "time_start": None,
        "time_end": None,
        "duration_minutes": None,
        "duration_explicitly_stated": False,
        "appointment_type": None,
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
        "diagnosis_or_impression_stated": "Hypertension artérielle et diabète de type 2, cible glycémique non atteinte",
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
    "notes_uncertain_items": ["Bilan sanguin de contrôle demandé (HbA1c, fonction rénale) dans 3 mois"],
}

MOCK_RESULT = {
    "analysis": "Suivi d'hypertension en cabinet; un bilan sanguin de contrôle est demandé.",
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une maladie chronique, hypertension artérielle",
            "confidence": "high",
            "explanation": "hypertension artérielle depuis 10 ans",
            "supporting_quote": "hypertension artérielle depuis 10 ans",
            "needs_confirmation": [],
        },
    ],
    "other_possible_codes": [
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


def _mock_response(payload=MOCK_RESULT):
    return fake_chat_result(payload)


def _extract(client: TestClient, *, patient_id: int, summary=MOCK_SUMMARY_RESULT, billing=MOCK_RESULT, side_effect=None):
    """POSTs /extract with the model mocked; returns the response and the mocked chat."""
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(
            side_effect=side_effect or [_mock_response(summary), _mock_response(billing)]
        )
        response = client.post(
            "/extract",
            json={
                "transcript": SAMPLE_TRANSCRIPT,
                "patient_id": patient_id,
                "source": {"system": "plume_ai", "encounter_id": "enc-123"},
            },
        )
    return response, mock_get_client.return_value.chat


# Patients are globally unique by NAM now, and the test DB is shared across the whole
# session (see conftest.py) — a default of None generates a fresh NAM per call so tests
# that don't care about the exact value never collide with each other.
_ramq_numbers = itertools.count(1)


async def _seed_patient(*, ramq_number=None, full_name="Louise Tremblay"):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            ramq_number=ramq_number or f"EXTR{next(_ramq_numbers):08d}",
            date_of_birth=date(1958, 2, 15),
            gender=Gender.FEMALE,
            is_vulnerable=False,
        )


async def test_extract_endpoint_end_to_end():
    # billing_codes is now a two-stage pipeline (consultation_summary, then billing_codes
    # off that summary) — two chat-completion calls happen, so mock two responses in order.
    with TestClient(app) as client:
        patient = await _seed_patient()
        response, chat = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    body = response.json()
    assert [c["code"] for c in body["billing"]["codes"]] == ["TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"]
    # The billing prompt lists the retrieved candidates only, not the whole reference table.
    billing_user_message = chat.call_args_list[1].kwargs["messages"][1].content
    assert "TEST-BP-MGMT" in billing_user_message
    assert "TEST-CONSULT-NEW" not in billing_user_message  # not relevant to this transcript
    # One run for the chosen patient, transcript stored once, a result row per stage.
    async with session_scope() as session:
        run = await session.get(ExtractionRun, body["extraction_run_id"])
        tasks = (
            await session.scalars(select(ExtractionRunResult.task).where(ExtractionRunResult.run_id == run.id))
        ).all()
    assert run.patient_id == patient.id
    assert run.user_id == 1
    assert sorted(tasks) == ["billing_codes", "consultation_summary"]
    # The transcript lives on the run's encounter: a paste, with no external note id.
    async with session_scope() as session:
        encounter = await session.get(Encounter, run.encounter_id)
    assert encounter.note_text == SAMPLE_TRANSCRIPT
    assert encounter.content_hash == content_hash(SAMPLE_TRANSCRIPT)
    assert encounter.channel == "paste"
    assert encounter.source_system == "plume_ai"
    assert encounter.external_note_id is None
    assert encounter.external_encounter_id == "enc-123"
    assert encounter.patient_id == patient.id
    assert encounter.service_date is None
    # MOCK_SUMMARY_RESULT's encounter_setting.date is null -> must stay null, never "today".
    assert body["encounter_date"] is None
    assert body["encounter_date_raw"] is None
    assert body["summary"]["short_description"] == MOCK_SUMMARY_RESULT["short_description"]
    assert body["summary"]["procedures"] == []
    assert body["summary"]["referral"] is None


async def test_extract_endpoint_sets_the_encounters_service_date_from_the_summary():
    summary = {**MOCK_SUMMARY_RESULT, "encounter_setting": {**MOCK_SUMMARY_RESULT["encounter_setting"], "date": "2026-02-10"}}
    with TestClient(app) as client:
        patient = await _seed_patient()
        response, _ = _extract(client, patient_id=patient.id, summary=summary)

    assert response.status_code == 200
    async with session_scope() as session:
        run = await session.get(ExtractionRun, response.json()["extraction_run_id"])
        encounter = await session.get(Encounter, run.encounter_id)
    assert encounter.service_date == date(2026, 2, 10)


async def test_extract_endpoint_records_a_pipeline_failure_on_the_encounter():
    with TestClient(app, raise_server_exceptions=False) as client:
        patient = await _seed_patient()
        response, _ = _extract(client, patient_id=patient.id, side_effect=RuntimeError("model unavailable"))

    assert response.status_code == 500
    async with session_scope() as session:
        encounter = await session.scalar(
            select(Encounter).where(Encounter.patient_id == patient.id).order_by(Encounter.id.desc())
        )
        runs = (await session.scalars(select(ExtractionRun).where(ExtractionRun.encounter_id == encounter.id))).all()
    assert encounter.extraction_error == "RuntimeError: model unavailable"
    assert runs == []


async def test_extract_endpoint_resolves_fees_from_the_real_candidate_data():
    # The mocked model response above carries no fee data at all (the model is never asked
    # for one — see app/ramq_codes/models.py's ExtractedCode.fees server_only marker); fees
    # must come from the pipeline's post-extraction resolution step
    # (FeeResolver) reading the real fixture data (tests/fixtures/reference_data_test.json),
    # not from the mock.
    with TestClient(app) as client:
        patient = await _seed_patient()
        response, _ = _extract(client, patient_id=patient.id)

    assert response.status_code == 200
    codes = {c["code"]: c for c in response.json()["billing"]["codes"]}
    assert codes["TEST-BP-MGMT"]["fees"] == [
        {
            "amount": 33.15,
            "amount_text": "33,15",
            "role": None,
            "unit": "dollars",
            "context": "Par visite de suivi",
            "lieux": [],
            "majoration": None,
        }
    ]
    assert codes["TEST-BLOODWORK-ORDER"]["fees"] == []


async def test_extract_endpoint_requires_a_known_patient_id():
    with TestClient(app) as client:
        response, _ = _extract(client, patient_id=999999)

    assert response.status_code == 404


# -- model resolution and unusable output (app/llm/structured.py) -----------------------


async def _summarize(summarizer: ConsultationSummarizer, payload=MOCK_SUMMARY_RESULT, **chat_result):
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(return_value=fake_chat_result(payload, **chat_result))
        await summarizer.summarize(SAMPLE_TRANSCRIPT)
    return mock_get_client


async def test_a_call_uses_its_default_model():
    mock_get_client = await _summarize(ConsultationSummarizer())

    mock_get_client.assert_called_once_with(ConsultationSummarizer.DEFAULT_MODEL)


async def test_the_model_env_override_beats_the_default(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_CONSULTATION_SUMMARY", "qwen3-32b")
    mock_get_client = await _summarize(ConsultationSummarizer())

    mock_get_client.assert_called_once_with("qwen3-32b")


async def test_an_explicit_model_beats_the_env_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_CONSULTATION_SUMMARY", "qwen3-32b")
    mock_get_client = await _summarize(ConsultationSummarizer(model="llama-70b"))

    mock_get_client.assert_called_once_with("llama-70b")


async def test_the_call_asks_for_its_output_models_strict_schema():
    mock_get_client = await _summarize(ConsultationSummarizer())

    response_format = mock_get_client.return_value.chat.call_args.kwargs["response_format"]
    assert response_format["json_schema"]["name"] == "consultation_summary"
    assert response_format["json_schema"]["strict"] is True
    assert "clinical_summary" in response_format["json_schema"]["schema"]["properties"]


@pytest.mark.parametrize(
    ("content", "finish_reason"),
    [
        ("{not json", "stop"),
        ('{"short_description": 3}', "stop"),
        ('{"codes": [', "length"),
        ("{}", "content_filter"),
    ],
)
async def test_unusable_output_raises_extraction_output_error_with_the_raw_content(content, finish_reason):
    with pytest.raises(ExtractionOutputError) as excinfo:
        await _summarize(ConsultationSummarizer(), content, finish_reason=finish_reason)

    assert excinfo.value.raw_content == content
    assert excinfo.value.finish_reason == finish_reason
