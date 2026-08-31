"""Exercises the three-stage billing_codes pipeline (app/extraction/pipeline.py): a
transcript is summarized via consultation_summary first, the patient/physician context is
resolved, and billing_codes then runs off the structured summary, the raw transcript, and
that resolved BillingContext — never the summary's rendered text alone (see
BillingCodesInput's docstring for why both reach the selection step)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.extraction.pipeline import run_billing_codes_pipeline
from app.postgresdb import User, UserRole
from app.ramq_codes import BillingContext, PhysicianContext
from app.summary import render_for_billing_codes
from tests.test_consultation_summary import MOCK_RESULT as MOCK_SUMMARY_RESULT
from tests.test_extraction import MOCK_RESULT as MOCK_BILLING_RESULT

TRANSCRIPT = (
    "Patiente de 58 ans suivie pour diabète de type 2, se présente en cabinet sur "
    "rendez-vous pour son suivi trimestriel. Tension artérielle mesurée à 138/86."
)

USER = User(id=1, email="doc@example.test", hashed_password="x", full_name="Dr. Doe", role=UserRole.PHYSICIAN)


class _NoopPatientSuggestionService:
    async def suggest(self, extracted, *, physician_id, on_date):
        return None


class _FakeContextBuilder:
    def __init__(self, context: BillingContext):
        self._context = context
        self.build_calls: list[dict] = []

    async def build(self, *, user, matched_patient_id, encounter_date):
        self.build_calls.append(
            {"user": user, "matched_patient_id": matched_patient_id, "encounter_date": encounter_date}
        )
        return self._context


def _response(payload):
    return SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(payload)),
        raw={
            "model": "mistral-small-latest",
            "choices": [SimpleNamespace(finish_reason="stop")],
        },
    )


async def _run_pipeline(context: BillingContext = BillingContext()):
    context_builder = _FakeContextBuilder(context)
    with patch("app.extraction.engine.get_client") as mock_get_client:
        mock_get_client.return_value.achat = AsyncMock(side_effect=[
            _response(MOCK_SUMMARY_RESULT),
            _response(MOCK_BILLING_RESULT),
        ])
        summary_result, billing_result, patient_suggestion = await run_billing_codes_pipeline(
            TRANSCRIPT,
            user=USER,
            context_builder=context_builder,
            patient_suggestion_service=_NoopPatientSuggestionService(),
        )
    return summary_result, billing_result, patient_suggestion, mock_get_client, context_builder


async def test_pipeline_runs_all_three_stages():
    summary_result, billing_result, patient_suggestion, mock_get_client, _ = await _run_pipeline()

    assert summary_result.task == "consultation_summary"
    assert billing_result.task == "billing_codes"
    assert patient_suggestion is None
    assert mock_get_client.return_value.achat.call_count == 2


async def test_consultation_summary_stage_sees_the_raw_transcript():
    summary_result, _billing_result, _p, mock_get_client, _ = await _run_pipeline()

    first_user_message = mock_get_client.return_value.achat.call_args_list[0].kwargs["messages"][1].content
    assert TRANSCRIPT in first_user_message


async def test_billing_codes_stage_sees_both_the_rendered_summary_and_the_raw_transcript():
    summary_result, _billing_result, _p, mock_get_client, _ = await _run_pipeline()

    second_user_message = mock_get_client.return_value.achat.call_args_list[1].kwargs["messages"][1].content
    rendered_summary = render_for_billing_codes(summary_result.result)
    # billing_codes must see both — the whole point of passing the transcript through
    # instead of bottlenecking selection on whatever the summarizer kept.
    assert rendered_summary in second_user_message
    assert TRANSCRIPT in second_user_message


async def test_billing_codes_stage_states_known_context_facts():
    context = BillingContext(physician=PhysicianContext(number_of_patients=320))

    _s, _b, _p, mock_get_client, _ = await _run_pipeline(context)

    second_user_message = mock_get_client.return_value.achat.call_args_list[1].kwargs["messages"][1].content
    assert "320 patients" in second_user_message


async def test_context_builder_receives_the_encounter_date_parsed_from_the_summary():
    # MOCK_SUMMARY_RESULT's encounter_setting.date is null in this fixture, so the pipeline
    # must fall back to passing None through rather than substituting today's date onto the
    # context builder call — see app/extraction/encounter_date.py's "never guess" stance.
    _s, _b, _p, _client, context_builder = await _run_pipeline()

    assert context_builder.build_calls == [
        {"user": USER, "matched_patient_id": None, "encounter_date": None}
    ]
