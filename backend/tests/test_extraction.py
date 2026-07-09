"""Exercises the full pipeline (prompt building -> schema -> parsing -> storage -> API)
against a mocked Claude response, since no ANTHROPIC_API_KEY is available in this
environment. Once a key is configured, see scripts/try_extraction.py for a live smoke test."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.extraction.engine import run_extraction
from app.main import app
from app.tasks.registry import get_task

SAMPLE_TRANSCRIPT = (
    "patient: I'm here for my blood pressure follow-up, and some headaches.\n"
    "doctor: Let's start with the headaches. How long, how often, how bad?\n"
    "patient: About two weeks, comes and goes, maybe a 4 out of 10.\n"
    "doctor: Your blood pressure today is 138/88, a bit high. Let's adjust your amlodipine "
    "and order routine bloodwork to check your kidney function.\n"
)

MOCK_RESULT = {
    "codes": [
        {
            "code": "PLACEHOLDER-BP-MGMT",
            "description": "Chronic disease management, hypertension",
            "confidence": 0.9,
            "supporting_quote": "adjust your amlodipine",
        },
        {
            "code": "PLACEHOLDER-BLOODWORK-ORDER",
            "description": "Ordering and reviewing routine bloodwork",
            "confidence": 0.85,
            "supporting_quote": "order routine bloodwork",
        },
    ],
    "notes": None,
}


def _mock_response():
    return SimpleNamespace(
        stop_reason="end_turn",
        model="claude-opus-4-8",
        content=[SimpleNamespace(type="text", text=json.dumps(MOCK_RESULT))],
    )


def test_run_extraction_parses_mocked_response():
    task = get_task("billing_codes")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _mock_response()
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert result.task == "billing_codes"
    assert [c.code for c in result.result.codes] == [
        "PLACEHOLDER-BP-MGMT",
        "PLACEHOLDER-BLOODWORK-ORDER",
    ]
    # The prompt actually sent to Claude should have narrowed candidates via keyword match,
    # not dumped the whole reference table — confirm the call args reflect that.
    call_kwargs = mock_get_client.return_value.messages.create.call_args.kwargs
    user_message = call_kwargs["messages"][0]["content"]
    assert "PLACEHOLDER-BP-MGMT" in user_message
    assert "PLACEHOLDER-CONSULT-NEW" not in user_message  # not relevant to this transcript


def test_run_extraction_enriches_prices_from_reference_table():
    """Price must come from the reference table lookup, not from the (mocked) model
    output — the mock response above doesn't include price_cad at all."""
    task = get_task("billing_codes")
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _mock_response()
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    prices = {c.code: c.price_cad for c in result.result.codes}
    assert prices == {
        "PLACEHOLDER-BP-MGMT": 35.75,
        "PLACEHOLDER-BLOODWORK-ORDER": 18.25,
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
        mock_get_client.return_value.messages.create.return_value = SimpleNamespace(
            stop_reason="end_turn",
            model="claude-opus-4-8",
            content=[SimpleNamespace(type="text", text=json.dumps(mock_result))],
        )
        result = run_extraction(task, SAMPLE_TRANSCRIPT)

    assert result.result.codes[0].price_cad is None
    assert result.result.total_price_cad is None


def test_extract_endpoint_end_to_end():
    # DATABASE_URL is bound to a SQLAlchemy engine at import time (app/db.py), so it can't
    # be swapped per-test via monkeypatch here — this exercises the real dev DB's schema.
    # Using TestClient as a context manager triggers the FastAPI lifespan (init_db()).
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.messages.create.return_value = _mock_response()
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
