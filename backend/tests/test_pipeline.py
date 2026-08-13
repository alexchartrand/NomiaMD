"""Exercises the two-stage billing_codes pipeline (app/extraction/pipeline.py): a
transcript is summarized via consultation_summary first, and billing_codes then runs off
that summary's rendered text — never the raw transcript directly."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.extraction.pipeline import run_billing_codes_pipeline
from app.summary import render_for_billing_codes
from tests.test_consultation_summary import MOCK_RESULT as MOCK_SUMMARY_RESULT
from tests.test_extraction import MOCK_RESULT as MOCK_BILLING_RESULT

TRANSCRIPT = (
    "Patiente de 58 ans suivie pour diabète de type 2, se présente en cabinet sur "
    "rendez-vous pour son suivi trimestriel. Tension artérielle mesurée à 138/86."
)


def _response(payload):
    return SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(payload)),
        raw={
            "model": "mistral-small-latest",
            "choices": [SimpleNamespace(finish_reason="stop")],
        },
    )


def test_pipeline_feeds_rendered_summary_into_billing_codes():
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.chat.side_effect = [
            _response(MOCK_SUMMARY_RESULT),
            _response(MOCK_BILLING_RESULT),
        ]
        summary_result, billing_result = run_billing_codes_pipeline(TRANSCRIPT)

    assert summary_result.task == "consultation_summary"
    assert billing_result.task == "billing_codes"

    chat = mock_get_client.return_value.chat
    assert chat.call_count == 2

    first_user_message = chat.call_args_list[0].kwargs["messages"][1].content
    assert TRANSCRIPT in first_user_message

    second_user_message = chat.call_args_list[1].kwargs["messages"][1].content
    rendered_summary = render_for_billing_codes(summary_result.result)
    # billing_codes must have been called with the rendered summary, not the raw
    # transcript — the whole point of the two-stage pipeline.
    assert rendered_summary in second_user_message
    assert TRANSCRIPT not in second_user_message
