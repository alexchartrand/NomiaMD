"""Sanity-checks the fake LLM dev server's response shape — it needs to look enough like a
real Mistral chat-completions response that run_extraction() (app/extraction/engine.py)
accepts it unmodified."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fastapi.testclient import TestClient

import fake_llm_server

client = TestClient(fake_llm_server.app)


def _request_body(user_message: str) -> dict:
    # content-as-list-of-chunks, matching what the Mistral client (llama_index's
    # MistralAI) actually sends over the wire — see fake_llm_server._content_to_text.
    return {
        "model": "fake-llm",
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "system prompt"}]},
            {"role": "user", "content": [{"type": "text", "text": user_message}]},
        ],
    }


def test_picks_candidates_from_prompt():
    user_message = (
        "Candidate RAMQ codes:\n"
        "- 15801: Visite de prise en charge [when to use: Prise en charge d'un nouveau patient]\n"
        "- 08579: Révision d'un examen\n"
        "- 00260: Blocage du ganglion stellaire [fees: 174.90 — Pour un déplacement entre 8h et 18h]\n\n"
        "Transcript:\nPatient exemple."
    )
    response = client.post("/v1/chat/completions", json=_request_body(user_message))
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["finish_reason"] == "stop"

    content = json.loads(body["choices"][0]["message"]["content"])
    assert len(content["codes"]) == fake_llm_server.PICK
    assert content["codes"][0]["code"] == "15801"
    assert content["codes"][0]["description"] == "Visite de prise en charge"
    assert "supporting_quote" in content["codes"][0]
    assert content["codes"][0]["fee"] == {"amount": None, "when_to_use": None, "majoration": None}


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
