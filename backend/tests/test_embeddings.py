"""app/llm/embeddings.py's provider selection from EMBEDDING_PROVIDER, OpenAIEmbeddingClient
against a real AsyncOpenAI whose HTTP transport is mocked, and the startup dimension guard
(app/llm/embedding_guard.py) against real temp LanceDB tables' vector columns. The guard's
probe goes through a fixed-dimension fake embedding client."""

import json

import httpx
import lancedb
import pyarrow as pa
import pytest
from openai import AsyncOpenAI

from app.lancedb.database import vector_dimension
from app.llm import (
    EmbeddingDimensionGuard,
    EmbeddingDimensionMismatchError,
    UnknownEmbeddingProviderError,
    UsageRecorder,
    call_purpose,
    embedding_provider,
    get_embedding_client,
    usage_scope,
)
from app.llm.mistral import MistralEmbeddingProvider
from app.llm.openai_client import OpenAIEmbeddingClient
from app.llm.openai_compatible import OpenAICompatibleEmbeddingProvider
from tests.llm_helpers import FakeEmbeddingClient


@pytest.fixture(autouse=True)
def fresh_embedding_cache():
    get_embedding_client.cache_clear()
    yield
    get_embedding_client.cache_clear()


def test_defaults_to_mistral(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "mistral-embed")
    assert isinstance(embedding_provider(), MistralEmbeddingProvider)
    client = get_embedding_client()
    assert isinstance(client, OpenAIEmbeddingClient)
    assert client.model_name == "mistral-embed"
    assert str(client._client.base_url) == "https://api.mistral.ai/v1/"


def test_mistral_ignores_the_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "mistral-embed")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8081/v1")
    assert str(get_embedding_client()._client.base_url) == "https://api.mistral.ai/v1/"


def test_selects_openai_compatible(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8081/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    assert isinstance(embedding_provider(), OpenAICompatibleEmbeddingProvider)
    client = get_embedding_client()
    assert str(client._client.base_url) == "http://localhost:8081/v1/"
    assert client.model_name == "BAAI/bge-m3"


@pytest.mark.parametrize("missing", ["EMBEDDING_API_KEY", "EMBEDDING_MODEL"])
def test_mistral_requires_key_and_model(monkeypatch, missing):
    # Not the SDK's own OPENAI_API_KEY fallback: a missing role-based key fails loudly.
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "mistral-embed")
    monkeypatch.setenv("OPENAI_API_KEY", "sdk-fallback-key")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY.*EMBEDDING_MODEL"):
        get_embedding_client()


@pytest.mark.parametrize("missing", ["EMBEDDING_ENDPOINT", "EMBEDDING_MODEL"])
def test_openai_compatible_requires_endpoint_and_model(monkeypatch, missing):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8081/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="EMBEDDING_ENDPOINT.*EMBEDDING_MODEL"):
        get_embedding_client()


def test_unknown_provider_fails_with_clear_error(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
    with pytest.raises(UnknownEmbeddingProviderError, match="'cohere'.*mistral.*openai_compatible"):
        embedding_provider()


async def test_unknown_provider_fails_at_startup(monkeypatch):
    from app.bootstrap import application_services

    monkeypatch.setenv("EMBEDDING_PROVIDER", "nope")
    with pytest.raises(UnknownEmbeddingProviderError):
        async with application_services():
            pass


# -- OpenAIEmbeddingClient over a mocked transport -----------------------------------------


def _client(*, usage: dict | None = None):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        # Out of order on purpose: the client must restore input order from `index`.
        data = [
            {"object": "embedding", "index": i, "embedding": [float(i), 1.0]}
            for i in reversed(range(len(body["input"])))
        ]
        response = {"object": "list", "model": body["model"], "data": data}
        if usage is not None:
            response["usage"] = usage
        return httpx.Response(200, json=response)

    sdk = AsyncOpenAI(
        api_key="test-key",
        base_url="http://embed.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return OpenAIEmbeddingClient(sdk, provider="test", model="embed-model", recorder=UsageRecorder()), requests


async def test_embed_batches_every_text_in_one_float_request_and_keeps_input_order():
    client, requests = _client(usage={"prompt_tokens": 7, "total_tokens": 7})

    vectors = await client.embed(["a", "b", "c"])

    assert vectors == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]
    [body] = requests
    assert body == {"model": "embed-model", "input": ["a", "b", "c"], "encoding_format": "float"}


async def test_embed_records_input_tokens_and_purpose():
    client, _ = _client(usage={"prompt_tokens": 7, "total_tokens": 7})

    with usage_scope() as scope, call_purpose("billing_codes.retrieval"):
        await client.embed_query("a")

    [call] = scope.records
    assert call.kind == "embedding"
    assert call.purpose == "billing_codes.retrieval"
    assert (call.input_tokens, call.output_tokens) == (7, None)
    assert call.model == "embed-model"


async def test_embed_tolerates_a_response_without_usage():
    client, _ = _client(usage=None)

    with usage_scope() as scope:
        await client.embed(["a"])

    assert scope.records[0].input_tokens is None


async def test_embed_of_nothing_makes_no_call():
    client, requests = _client()

    assert await client.embed([]) == []
    assert requests == []


# -- startup dimension guard ---------------------------------------------------------------


async def _table_with_vector_dimension(tmp_path, name: str, dimension: int):
    connection = await lancedb.connect_async(str(tmp_path))
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dimension)),
    ])
    return await connection.create_table(name, schema=schema)


async def test_vector_dimension_reads_the_fixed_size_list(tmp_path):
    table = await _table_with_vector_dimension(tmp_path, "codes_test", 1024)
    assert await vector_dimension(table) == 1024


async def test_guard_passes_when_every_table_matches(tmp_path):
    codes = await _table_with_vector_dimension(tmp_path, "codes_test", 8)
    documents = await _table_with_vector_dimension(tmp_path, "documents-embeddings", 8)
    guard = EmbeddingDimensionGuard(FakeEmbeddingClient(default=[0.0] * 8, model_name="fake"))
    await guard.check({
        "codes_test": await vector_dimension(codes),
        "documents-embeddings": await vector_dimension(documents),
    })


async def test_guard_raises_naming_the_model_and_the_mismatched_table(tmp_path):
    codes = await _table_with_vector_dimension(tmp_path, "codes_test", 1024)
    documents = await _table_with_vector_dimension(tmp_path, "documents-embeddings", 768)
    guard = EmbeddingDimensionGuard(FakeEmbeddingClient(default=[0.0] * 768, model_name="bge-local"))
    with pytest.raises(EmbeddingDimensionMismatchError) as excinfo:
        await guard.check({
            "codes_test": await vector_dimension(codes),
            "documents-embeddings": await vector_dimension(documents),
        })
    message = str(excinfo.value)
    assert "'bge-local'" in message and "768-dim" in message
    assert "codes_test (dim 1024)" in message
    assert "documents-embeddings" not in message
