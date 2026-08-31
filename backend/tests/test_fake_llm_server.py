"""Sanity-checks the fake LLM dev server's response shape — it needs to look enough like a
real Mistral chat-completions response that run_extraction() (app/extraction/engine.py)
accepts it unmodified."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fastapi.testclient import TestClient

import fake_llm_server

from app.summary import ConsultationSummaryResult
from app.summary.task import SYSTEM_PROMPT as SUMMARY_SYSTEM_PROMPT

client = TestClient(fake_llm_server.app)


def _request_body(user_message: str, system_message: str = "system prompt") -> dict:
    # content-as-list-of-chunks, matching what the Mistral client (llama_index's
    # MistralAI) actually sends over the wire — see fake_llm_server._content_to_text.
    return {
        "model": "fake-llm",
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system_message}]},
            {"role": "user", "content": [{"type": "text", "text": user_message}]},
        ],
    }


def test_picks_candidates_from_prompt():
    user_message = (
        "Candidate RAMQ codes:\n"
        "- 15801 | B > Visite de prise en charge\n"
        "  Visite de prise en charge\n"
        "  Utilisation : Prise en charge d'un nouveau patient\n"
        "- 08579 | B > Révision d'un examen\n"
        "  Révision d'un examen\n"
        "- 00260 | B > Blocage du ganglion stellaire\n"
        "  Blocage du ganglion stellaire\n"
        "  Tarifs : 174.90 — Pour un déplacement entre 8h et 18h\n\n"
        "Consultation summary (normalized view):\nRésumé.\n\n"
        "Raw transcript (detail-of-record):\nPatient exemple."
    )
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["finish_reason"] == "stop"

    content = json.loads(body["choices"][0]["message"]["content"])
    assert len(content["codes"]) == fake_llm_server.PICK
    assert content["codes"][0]["code"] == "15801"
    assert content["codes"][0]["description"] == "Visite de prise en charge"
    assert "explanation" in content["codes"][0]
    assert content["codes"][0]["confidence"] == "medium"
    assert "supporting_quote" in content["codes"][0]
    assert content["codes"][0]["needs_confirmation"] == []
    assert content["codes"][0]["fee"] == {"amount": None, "when_to_use": None, "majoration": None}


def test_picks_up_the_real_fee_from_the_tarifs_line():
    user_message = (
        "Candidate RAMQ codes:\n"
        "- 15801 | B > Visite\n"
        "  Visite\n"
        "- 00260 | B > Blocage du ganglion stellaire\n"
        "  Blocage du ganglion stellaire\n"
        "  Tarifs : 174.90 — Pour un déplacement entre 8h et 18h\n\n"
        "Consultation summary (normalized view):\nRésumé.\n\n"
        "Raw transcript (detail-of-record):\nPatient exemple."
    )
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    content = json.loads(response.json()["choices"][0]["message"]["content"])

    by_code = {c["code"]: c for c in content["codes"]}
    assert by_code["00260"]["fee"] == {
        "amount": 174.90,
        "when_to_use": "Pour un déplacement entre 8h et 18h",
        "majoration": None,
    }


def test_no_candidates_returns_empty_codes_with_note():
    user_message = "Candidate RAMQ codes:\n\nTranscript:\nRien de pertinent."
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    content = json.loads(response.json()["choices"][0]["message"]["content"])
    assert content["codes"] == []
    assert content["notes"]


def test_consultation_summary_request_echoes_header_fields_as_valid_result():
    transcript = (
        "**Patient :** Desjardins, Roch — 45 ans (H)\n"
        "**NAM :** DESR81021001\n"
        "**Dossier :** #CLI-2026-01220\n"
        "**Date/heure :** 10 février 2026, 09h15\n"
    )
    user_message = f"Transcript:\n{transcript}\n\nExtract the structured facts per your instructions."

    response = client.post(
        "/v1/chat/completions", json=_request_body(user_message, system_message=SUMMARY_SYSTEM_PROMPT)
    )
    assert response.status_code == 200

    content = json.loads(response.json()["choices"][0]["message"]["content"])
    # Must parse as a real ConsultationSummaryResult — this is what run_extraction() feeds
    # ConsultationSummaryTask.parse() with.
    result = ConsultationSummaryResult.model_validate(content)

    assert result.patient_information.name_as_stated == "Desjardins, Roch"
    assert result.patient_information.ramq_number_as_stated == "DESR81021001"
    assert result.patient_information.age_years == 45
    assert result.encounter_setting.date == "10 février 2026"


def test_billing_codes_request_is_not_misdetected_as_consultation_summary():
    from app.ramq_codes.task import SYSTEM_PROMPT as BILLING_SYSTEM_PROMPT

    assert fake_llm_server._classify_request(BILLING_SYSTEM_PROMPT, "") != "consultation_summary"


def test_models_endpoint():
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "fake-llm"
