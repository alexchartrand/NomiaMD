"""app/llm/: provider selection from LLM_PROVIDER and reading either provider's raw chat
response. Builds real llama-index clients (no network — construction doesn't call out)."""

from types import SimpleNamespace

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.llms.mistralai import MistralAI
from llama_index.llms.openai_like import OpenAILike
from openai.types.chat import ChatCompletion as OpenAIChatCompletion

from app.llm import ChatResponseReader, UnknownChatProviderError, chat_provider, get_chat_llm
from app.llm.mistral import MistralChatProvider
from app.llm.openai_compatible import OpenAICompatibleChatProvider


@pytest.fixture(autouse=True)
def fresh_llm_cache():
    get_chat_llm.cache_clear()
    yield
    get_chat_llm.cache_clear()


def test_defaults_to_mistral(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    assert isinstance(chat_provider(), MistralChatProvider)
    llm = get_chat_llm("mistral-small-latest")
    assert isinstance(llm, MistralAI)
    assert llm.temperature == 0
    assert llm.max_tokens == 4096


def test_selects_openai_compatible(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:8080/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert isinstance(chat_provider(), OpenAICompatibleChatProvider)
    llm = get_chat_llm("some-model")
    assert isinstance(llm, OpenAILike)
    assert llm.api_base == "http://localhost:8080/v1"
    assert llm.temperature == 0
    assert llm.max_tokens == 4096
    assert llm.metadata.is_chat_model


def test_temperature_override_gets_its_own_client(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    assert get_chat_llm("m", temperature=0.5).temperature == 0.5
    assert get_chat_llm("m") is not get_chat_llm("m", temperature=0.5)
    assert get_chat_llm("m") is get_chat_llm("m")


def test_openai_compatible_requires_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="LLM_ENDPOINT"):
        get_chat_llm("some-model")


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


def _message(content: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.ASSISTANT, content=content)


def test_reader_on_mistral_shaped_response():
    # llama-index's MistralAI: raw=dict(response), choices are SDK objects.
    response = ChatResponse(
        message=_message('{"codes": []}'),
        raw={"model": "mistral-small-latest", "choices": [SimpleNamespace(finish_reason="stop")]},
    )
    completion = ChatResponseReader().read(response)
    assert completion.content == '{"codes": []}'
    assert completion.finish_reason == "stop"
    assert completion.model == "mistral-small-latest"


def test_reader_on_openai_shaped_response():
    # OpenAILike: raw is the OpenAI SDK's ChatCompletion object itself.
    raw = OpenAIChatCompletion.model_validate({
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen-local",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": '{"codes": []}'},
            "finish_reason": "length",
        }],
    })
    completion = ChatResponseReader().read(ChatResponse(message=_message('{"codes": []}'), raw=raw))
    assert completion.content == '{"codes": []}'
    assert completion.finish_reason == "length"
    assert completion.model == "qwen-local"
