"""Exercises the consultation_summary task against a mocked model response — same pattern
as test_extraction.py's billing_codes tests."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.extraction.engine import run_extraction
from app.main import app
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
    "chief_complaint": "Suivi trimestriel diabète de type 2 et hypertension artérielle",
    "visit_type": "sur rendez-vous",
    "visit_location": "cabinet",
    "acts_performed": ["Mesure de la tension artérielle"],
    "diagnoses": ["Diabète de type 2", "Hypertension artérielle"],
    "patient": {
        "age": 58,
        "vulnerable": None,
        "inscription_status": "inscrit",
        "evidence": "Patiente de 58 ans ... Patiente inscrite",
    },
    "plan": "Ajustement de la médication antihypertensive; bilan sanguin de contrôle dans 3 mois",
    "notes": None,
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
    assert result.result.chief_complaint == MOCK_RESULT["chief_complaint"]
    assert result.result.patient.age == 58
    assert result.result.patient.inscription_status == "inscrit"
    assert result.result.diagnoses == ["Diabète de type 2", "Hypertension artérielle"]


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
    assert body["result"]["patient"]["age"] == 58
    assert body["result"]["visit_type"] == "sur rendez-vous"
