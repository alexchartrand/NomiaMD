"""Exercises BillingPipeline (app/extraction/pipeline.py): a transcript is summarized via
consultation_summary first, the patient/physician context is resolved, candidates are
retrieved, and billing_codes then runs off the structured summary, the raw transcript, and
that resolved BillingContext — never the summary's rendered text alone (see the pipeline's
module docstring for why both reach the selection step)."""

from unittest.mock import AsyncMock, patch

from app.care_setting import CareSetting
from app.extraction import BillingPipeline
from app.postgresdb import User, UserRole
from app.ramq_codes import BillingContext, CandidateSet, CodeSelector, FeeResolver, PhysicianContext
from app.ramq_codes.models import Code
from app.summary import ConsultationSummarizer, render_for_billing_codes
from tests.test_consultation_summary import MOCK_RESULT as MOCK_SUMMARY_RESULT
from tests.test_extraction import MOCK_RESULT as MOCK_BILLING_RESULT
from tests.llm_helpers import fake_chat_result

TRANSCRIPT = (
    "Patiente de 58 ans suivie pour diabète de type 2, se présente en cabinet sur "
    "rendez-vous pour son suivi trimestriel. Tension artérielle mesurée à 138/86."
)

USER = User(id=1, email="doc@example.test", hashed_password="x", full_name="Dr. Doe", role=UserRole.PHYSICIAN)
PATIENT_ID = 42


class _FakeContextBuilder:
    def __init__(self, context: BillingContext):
        self._context = context
        self.build_calls: list[dict] = []

    async def build(self, *, user, patient_id, encounter_date, care_setting=None, shift=None, encounter_time=None):
        self.build_calls.append(
            {
                "user": user,
                "patient_id": patient_id,
                "encounter_date": encounter_date,
                "care_setting": care_setting,
                "shift": shift,
                "encounter_time": encounter_time,
            }
        )
        return self._context


class _FailingContextBuilder:
    async def build(self, **_kwargs):
        raise RuntimeError("profile lookup failed")


class _FakeRetriever:
    """Offers MOCK_BILLING_RESULT's two codes, so the model's answer survives parsing."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def aretrieve(self, summary, context) -> CandidateSet:
        self.calls.append((summary, context))
        numbers = ["TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"]
        return CandidateSet(candidates=[Code(number=n, description=n, header_path="x") for n in numbers], unresolved_axes=())


class _FeeRepository:
    def __init__(self, error: Exception | None = None):
        self._error = error

    async def list_by_numbers(self, numbers):
        if self._error:
            raise self._error
        return []


def _response(payload):
    return fake_chat_result(payload)


def _pipeline(context_builder, retriever=None, fee_repository=None) -> BillingPipeline:
    return BillingPipeline(
        summarizer=ConsultationSummarizer(),
        context_builder=context_builder,
        retriever=retriever or _FakeRetriever(),
        selector=CodeSelector(),
        fees=FeeResolver(fee_repository or _FeeRepository()),
    )


async def _run_pipeline(context: BillingContext = BillingContext(), **pipeline_kwargs):
    context_builder = pipeline_kwargs.pop("context_builder", None) or _FakeContextBuilder(context)
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(side_effect=[
            _response(MOCK_SUMMARY_RESULT),
            _response(MOCK_BILLING_RESULT),
        ])
        result = await _pipeline(context_builder, **pipeline_kwargs).run(
            TRANSCRIPT,
            user=USER,
            patient_id=PATIENT_ID,
        )
    return result, mock_get_client, context_builder


async def test_pipeline_runs_both_model_calls_and_returns_each_steps_result():
    result, mock_get_client, _ = await _run_pipeline()

    assert result.summary.short_description == MOCK_SUMMARY_RESULT["short_description"]
    assert [c.code for c in result.billing.codes] == ["TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"]
    assert (result.summary_model, result.billing_model) == ("mistral-small-latest", "mistral-small-latest")
    assert mock_get_client.return_value.chat.call_count == 2


async def test_the_retriever_gets_the_summary_and_the_resolved_context():
    context = BillingContext(physician=PhysicianContext(panel_size=320))
    retriever = _FakeRetriever()

    result, _client, _builder = await _run_pipeline(context, retriever=retriever)

    assert retriever.calls == [(result.summary, context)]


async def test_a_context_lookup_failure_degrades_to_an_empty_context():
    retriever = _FakeRetriever()

    result, _client, _builder = await _run_pipeline(context_builder=_FailingContextBuilder(), retriever=retriever)

    assert retriever.calls[0][1] == BillingContext()
    assert len(result.billing.codes) == 2


async def test_a_fee_lookup_failure_keeps_the_codes_with_no_fees():
    result, _client, _builder = await _run_pipeline(fee_repository=_FeeRepository(RuntimeError("lancedb down")))

    assert [c.fees for c in result.billing.codes] == [[], []]


async def test_consultation_summary_stage_sees_the_raw_transcript():
    _result, mock_get_client, _ = await _run_pipeline()

    first_user_message = mock_get_client.return_value.chat.call_args_list[0].kwargs["messages"][1].content
    assert TRANSCRIPT in first_user_message


async def test_billing_codes_stage_sees_both_the_rendered_summary_and_the_raw_transcript():
    result, mock_get_client, _ = await _run_pipeline()

    second_user_message = mock_get_client.return_value.chat.call_args_list[1].kwargs["messages"][1].content
    rendered_summary = render_for_billing_codes(result.summary)
    # billing_codes must see both — the whole point of passing the transcript through
    # instead of bottlenecking selection on whatever the summarizer kept.
    assert rendered_summary in second_user_message
    assert TRANSCRIPT in second_user_message


async def test_billing_codes_stage_states_known_context_facts():
    context = BillingContext(physician=PhysicianContext(panel_size=320))

    _result, mock_get_client, _ = await _run_pipeline(context)

    second_user_message = mock_get_client.return_value.chat.call_args_list[1].kwargs["messages"][1].content
    assert "320 patients" in second_user_message


async def test_context_builder_receives_the_encounter_date_parsed_from_the_summary():
    # MOCK_SUMMARY_RESULT's encounter_setting.date is null in this fixture, so the pipeline
    # must fall back to passing None through rather than substituting today's date onto the
    # context builder call — see app/extraction/encounter_date.py's "never guess" stance.
    _result, _client, context_builder = await _run_pipeline()

    assert context_builder.build_calls == [
        {
            "user": USER,
            "patient_id": PATIENT_ID,
            "encounter_date": None,
            "care_setting": None,
            "shift": None,
            "encounter_time": None,
        }
    ]


async def test_context_builder_receives_the_care_setting_the_caller_passed():
    context_builder = _FakeContextBuilder(BillingContext())
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(
            side_effect=[_response(MOCK_SUMMARY_RESULT), _response(MOCK_BILLING_RESULT)]
        )
        await _pipeline(context_builder).run(
            TRANSCRIPT,
            user=USER,
            patient_id=PATIENT_ID,
            care_setting=CareSetting.URGENCE,
        )

    assert context_builder.build_calls[0]["care_setting"] is CareSetting.URGENCE
