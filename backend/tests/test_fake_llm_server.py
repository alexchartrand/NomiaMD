"""Sanity-checks the fake LLM dev server's response shape — it needs to look enough like a
real OpenAI-compatible response that run_extraction() (app/extraction/engine.py) accepts
it unmodified."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fastapi.testclient import TestClient

import fake_llm_server

client = TestClient(fake_llm_server.app)


def _request_body(user_message: str) -> dict:
    return {
        "model": "fake-llm",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": user_message},
        ],
    }


def test_picks_candidates_from_prompt():
    user_message = (
        "Candidate RAMQ codes:\n"
        "- 15801: Visite de prise en charge (category: B — Consultation)\n"
        "- 08579: Révision d'un examen (category: Divers)\n"
        "- 00260: Blocage du ganglion stellaire (category: Anesthésie)\n\n"
        "Transcript:\nPatient exemple."
    )
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["finish_reason"] == "stop"

    content = json.loads(body["choices"][0]["message"]["content"])
    assert len(content["codes"]) == fake_llm_server.PICK
    assert content["codes"][0]["code"] == "15801"
    assert "supporting_quote" in content["codes"][0]


def test_no_candidates_returns_empty_codes_with_note():
    user_message = "Candidate RAMQ codes:\n\nTranscript:\nRien de pertinent."
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    content = json.loads(response.json()["choices"][0]["message"]["content"])
    assert content["codes"] == []
    assert content["notes"]


def test_models_endpoint():
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "fake-llm"
