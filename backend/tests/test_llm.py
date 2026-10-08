"""app/llm/: chat provider selection from LLM_PROVIDER, and OpenAIChatClient against a real
AsyncOpenAI whose HTTP transport is mocked — so the request body that would go over the wire
and the reading of both full and usage-less responses are pinned, with no network."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.llm import ChatMessage, UnknownChatProviderError, UsageRecorder, call_purpose, chat_provider, get_chat_client, usage_scope
from app.llm.mistral import MistralChatProvider
from app.llm.openai_client import MAX_TOKENS, OpenAIChatClient
from app.llm.openai_compatible import OpenAICompatibleChatProvider


@pytest.fixture(autouse=True)
def fresh_llm_cache():
    get_chat_client.cache_clear()
    yield
    get_chat_client.cache_clear()


def test_defaults_to_mistral(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert isinstance(chat_provider(), MistralChatProvider)
    client = get_chat_client("mistral-small-latest")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "mistral-small-latest"
    assert client.temperature == 0
    assert client.max_tokens == MAX_TOKENS == 4096
    assert str(client._client.base_url) == "https://api.mistral.ai/v1/"


def test_mistral_endpoint_override_is_the_server_root(monkeypatch):
    # LLM_ENDPOINT keeps the Mistral convention: the root, without /v1.
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ENDPOINT", "https://mistral.example/")
    assert str(get_chat_client("m")._client.base_url) == "https://mistral.example/v1/"


def test_selects_openai_compatible(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:8080/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert isinstance(chat_provider(), OpenAICompatibleChatProvider)
    client = get_chat_client("some-model")
    assert str(client._client.base_url) == "http://localhost:8080/v1/"
    assert client.temperature == 0


def test_temperature_override_gets_its_own_client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert get_chat_client("m", temperature=0.5).temperature == 0.5
    assert get_chat_client("m") is not get_chat_client("m", temperature=0.5)
    assert get_chat_client("m") is get_chat_client("m")


def test_openai_compatible_requires_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="LLM_ENDPOINT"):
        get_chat_client("some-model")


def test_unknown_provider_fails_with_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropicc")
    with pytest.raises(UnknownChatProviderError, match="'anthropicc'.*mistral.*openai_compatible"):
        chat_provider()


async def test_unknown_provider_fails_at_startup(monkeypatch):
    from app.bootstrap import application_services

    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(UnknownChatProviderError):
        async with application_services():
            pass


# -- OpenAIChatClient over a mocked transport ----------------------------------------------


def _completion(*, content='{"codes": []}', finish_reason="stop", usage: dict | None = None) -> dict:
    body = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "served-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _client(response_body: dict | None = None, *, status: int = 200, recorder: UsageRecorder | None = None):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(status, json=response_body or {"error": {"message": "boom"}})

    sdk = AsyncOpenAI(
        api_key="test-key",
        base_url="http://llm.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    client = OpenAIChatClient(sdk, provider="test", model="requested-model", temperature=0.0, recorder=recorder or UsageRecorder())
    return client, requests


async def test_chat_sends_messages_temperature_max_tokens_and_response_format():
    client, requests = _client(_completion(usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}))
    response_format = {"type": "json_schema", "json_schema": {"name": "t", "strict": True, "schema": {"type": "object"}}}

    await client.chat(
        [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")],
        response_format=response_format,
    )

    [body] = requests
    assert body["model"] == "requested-model"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 4096
    assert body["response_format"] == response_format


async def test_chat_omits_response_format_when_none_is_given():
    client, requests = _client(_completion())

    await client.chat([ChatMessage(role="user", content="hi")])

    assert "response_format" not in requests[0]


async def test_chat_reads_content_finish_reason_model_and_usage():
    client, _ = _client(_completion(finish_reason="length", usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}))

    result = await client.chat([ChatMessage(role="user", content="hi")])

    assert result.content == '{"codes": []}'
    assert result.finish_reason == "length"
    assert result.model == "served-model"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 3)
    assert result.latency_ms >= 0


async def test_chat_tolerates_a_response_without_usage():
    client, _ = _client(_completion(usage=None))

    result = await client.chat([ChatMessage(role="user", content="hi")])

    assert (result.usage.input_tokens, result.usage.output_tokens) == (None, None)


async def test_chat_records_one_call_with_tokens_latency_and_purpose():
    client, _ = _client(_completion(usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}))

    with usage_scope() as scope, call_purpose("consultation_summary"):
        await client.chat([ChatMessage(role="user", content="hi")])

    [call] = scope.records
    assert call.kind == "chat"
    assert call.provider == "test"
    assert call.model == "served-model"
    assert call.purpose == "consultation_summary"
    assert (call.input_tokens, call.output_tokens) == (12, 3)
    assert call.finish_reason == "stop"
    assert call.latency_ms >= 0
    assert call.error is None


async def test_chat_records_a_failed_call_then_reraises():
    client, _ = _client(status=500)

    with usage_scope() as scope, pytest.raises(Exception):
        await client.chat([ChatMessage(role="user", content="hi")])

    [call] = scope.records
    assert call.error is not None and "InternalServerError" in call.error
    assert call.input_tokens is None
