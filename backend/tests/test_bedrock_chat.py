"""app/llm/bedrock_chat.py: LLM_PROVIDER=bedrock selection, and BedrockChatClient against a
fake boto3 client — so the Converse request that would go over the wire (system split out,
the strict schema as `outputConfig.textFormat`) and the reading of its answer (text blocks
only, stop reasons as OpenAI finish reasons, metering) are pinned, with no network."""

import json

import pytest

from app.llm import ChatMessage, UsageRecorder, call_purpose, chat_provider, get_chat_client, usage_scope
from app.llm.bedrock_chat import BedrockChatClient, BedrockChatProvider
from app.llm.openai_client import MAX_TOKENS

MODEL = "us.anthropic.claude-sonnet-5-5"
MESSAGES = [ChatMessage(role="system", content="Réponds en JSON."), ChatMessage(role="user", content="Note")]
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "billing_codes",
        "strict": True,
        "schema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}}},
                   "required": ["codes"], "additionalProperties": False},
    },
}


@pytest.fixture(autouse=True)
def fresh_llm_cache():
    get_chat_client.cache_clear()
    yield
    get_chat_client.cache_clear()


class _FakeBedrockRuntime:
    def __init__(self, response=None, error=None):
        self.requests = []
        self._response = response
        self._error = error

    def converse(self, **request):
        self.requests.append(request)
        if self._error:
            raise self._error
        return self._response


def _response(*blocks, stop_reason="end_turn", usage=None):
    return {
        "output": {"message": {"role": "assistant", "content": list(blocks)}},
        "stopReason": stop_reason,
        "usage": usage if usage is not None else {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150},
    }


def _client(runtime):
    return BedrockChatClient(runtime, model=MODEL, temperature=0.0, recorder=UsageRecorder())


def test_selects_bedrock_without_an_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    assert isinstance(chat_provider(), BedrockChatProvider)
    client = get_chat_client(MODEL)
    assert isinstance(client, BedrockChatClient)
    assert client.model == MODEL
    assert client.temperature == 0
    assert client.max_tokens == MAX_TOKENS
    assert client._client.meta.region_name == "us-east-1"


async def test_request_splits_system_and_sends_the_schema_as_text_format():
    runtime = _FakeBedrockRuntime(_response({"text": '{"codes": []}'}))
    await _client(runtime).chat(MESSAGES, response_format=RESPONSE_FORMAT)

    [request] = runtime.requests
    assert request["modelId"] == MODEL
    assert request["system"] == [{"text": "Réponds en JSON."}]
    assert request["messages"] == [{"role": "user", "content": [{"text": "Note"}]}]
    assert request["inferenceConfig"] == {"temperature": 0.0, "maxTokens": MAX_TOKENS}
    text_format = request["outputConfig"]["textFormat"]
    assert text_format["type"] == "json_schema"
    assert text_format["structure"]["jsonSchema"]["name"] == "billing_codes"
    assert json.loads(text_format["structure"]["jsonSchema"]["schema"]) == RESPONSE_FORMAT["json_schema"]["schema"]


async def test_plain_chat_sends_no_system_or_output_config():
    runtime = _FakeBedrockRuntime(_response({"text": "Bonjour"}))
    await _client(runtime).chat([ChatMessage(role="user", content="Salut")])

    [request] = runtime.requests
    assert "system" not in request
    assert "outputConfig" not in request


async def test_refuses_a_response_format_converse_has_no_equivalent_for():
    runtime = _FakeBedrockRuntime(_response({"text": "{}"}))
    with pytest.raises(ValueError, match="json_object"):
        await _client(runtime).chat(MESSAGES, response_format={"type": "json_object"})
    assert runtime.requests == []


async def test_reads_the_text_blocks_and_skips_reasoning():
    runtime = _FakeBedrockRuntime(
        _response({"reasoningContent": {"reasoningText": {"text": "Je réfléchis"}}}, {"text": '{"codes": '}, {"text": "[]}"})
    )
    result = await _client(runtime).chat(MESSAGES, response_format=RESPONSE_FORMAT)

    assert result.content == '{"codes": []}'
    assert result.finish_reason == "stop"
    assert result.model == MODEL
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)


async def test_no_text_block_is_no_content():
    result = await _client(_FakeBedrockRuntime(_response())).chat(MESSAGES)
    assert result.content is None


@pytest.mark.parametrize(
    ("stop_reason", "finish_reason"),
    [("end_turn", "stop"), ("stop_sequence", "stop"), ("max_tokens", "length"), ("content_filtered", "content_filtered")],
)
async def test_maps_stop_reasons_to_openai_finish_reasons(stop_reason, finish_reason):
    runtime = _FakeBedrockRuntime(_response({"text": "{}"}, stop_reason=stop_reason))
    result = await _client(runtime).chat(MESSAGES)
    assert result.finish_reason == finish_reason


async def test_missing_usage_is_none_not_zero():
    runtime = _FakeBedrockRuntime(_response({"text": "{}"}, usage={}))
    result = await _client(runtime).chat(MESSAGES)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (None, None)


async def test_meters_each_call_with_its_purpose():
    runtime = _FakeBedrockRuntime(_response({"text": "{}"}))
    with usage_scope() as scope, call_purpose("billing_codes"):
        await _client(runtime).chat(MESSAGES)

    [record] = scope.records
    assert (record.kind, record.provider, record.model, record.purpose) == ("chat", "bedrock", MODEL, "billing_codes")
    assert (record.input_tokens, record.output_tokens, record.finish_reason) == (120, 30, "stop")
    assert record.error is None


async def test_a_failed_call_is_metered_then_raised():
    runtime = _FakeBedrockRuntime(error=RuntimeError("ThrottlingException"))
    with usage_scope() as scope, pytest.raises(RuntimeError):
        await _client(runtime).chat(MESSAGES)

    [record] = scope.records
    assert record.error == "RuntimeError: ThrottlingException"
    assert record.input_tokens is None
