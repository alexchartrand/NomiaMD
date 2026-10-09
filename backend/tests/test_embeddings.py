"""app/llm/embeddings.py's provider selection from EMBEDDING_PROVIDER, OpenAIEmbeddingClient
against a real AsyncOpenAI whose HTTP transport is mocked, BedrockEmbeddingClient against a
fake boto3 client, and the startup model guard (app/llm/embedding_guard.py) against real temp
LanceDB tables' schemas. The guard's probe goes through a fixed-dimension fake embedding
client."""

import io
import json

import httpx
import lancedb
import pyarrow as pa
import pytest
from openai import AsyncOpenAI

from app.lancedb.database import stored_embedding
from app.llm import (
    EmbeddingModelGuard,
    EmbeddingModelMismatchError,
    StoredEmbedding,
    UnknownEmbeddingProviderError,
    UsageRecorder,
    call_purpose,
    embedding_provider,
    get_embedding_client,
    usage_scope,
)
from app.llm.bedrock import BedrockEmbeddingClient, BedrockEmbeddingProvider, CohereEmbedV3Format, CohereEmbedV4Format
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


def test_selects_bedrock(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bedrock")
    monkeypatch.setenv("EMBEDDING_MODEL", "cohere.embed-v4:0")
    monkeypatch.setenv("BEDROCK_REGION", "ca-central-1")
    assert isinstance(embedding_provider(), BedrockEmbeddingProvider)
    client = get_embedding_client()
    assert isinstance(client, BedrockEmbeddingClient)
    assert client.identity == "bedrock:cohere.embed-v4:0"
    assert client._client.meta.region_name == "ca-central-1"


def test_bedrock_requires_a_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bedrock")
    with pytest.raises(RuntimeError, match="EMBEDDING_MODEL"):
        get_embedding_client()


def test_bedrock_refuses_a_model_it_has_no_request_format_for(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bedrock")
    monkeypatch.setenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
    with pytest.raises(ValueError, match="titan"):
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


# -- BedrockEmbeddingClient over a fake boto3 client ---------------------------------------


class _FakeBedrockRuntime:
    """Answers InvokeModel like bedrock-runtime does: a streaming body, the input token count
    in a response header. `payload` builds the answer from the request body."""

    def __init__(self, payload, *, input_tokens: int | None = 5):
        self._payload = payload
        self._input_tokens = input_tokens
        self.requests: list[dict] = []

    def invoke_model(self, **request):
        self.requests.append({**request, "body": json.loads(request["body"])})
        headers = {} if self._input_tokens is None else {"x-amzn-bedrock-input-token-count": str(self._input_tokens)}
        payload = self._payload(self.requests[-1]["body"])
        return {"body": io.BytesIO(json.dumps(payload).encode()), "ResponseMetadata": {"HTTPHeaders": headers}}


def _v4_payload(body: dict) -> dict:
    return {"embeddings": {"float": [[float(i), 1.0] for i in range(len(body["texts"]))]}}


async def test_bedrock_embeds_cohere_v4_queries_as_search_query():
    runtime = _FakeBedrockRuntime(_v4_payload)
    client = BedrockEmbeddingClient(
        runtime, model="cohere.embed-v4:0", embedding_format=CohereEmbedV4Format(), recorder=UsageRecorder()
    )

    vectors = await client.embed(["a", "b"])

    assert vectors == [[0.0, 1.0], [1.0, 1.0]]
    [request] = runtime.requests
    assert request["modelId"] == "cohere.embed-v4:0"
    # The corpus side is `search_document` (ramq-ingestion); same width and no truncation.
    assert request["body"] == {
        "texts": ["a", "b"],
        "input_type": "search_query",
        "embedding_types": ["float"],
        "output_dimension": 1024,
        "truncate": "NONE",
    }


async def test_bedrock_embeds_cohere_v3_queries():
    runtime = _FakeBedrockRuntime(lambda body: {"embeddings": [[1.0] for _ in body["texts"]]})
    client = BedrockEmbeddingClient(
        runtime, model="cohere.embed-multilingual-v3", embedding_format=CohereEmbedV3Format(), recorder=UsageRecorder()
    )

    assert await client.embed(["a"]) == [[1.0]]
    assert runtime.requests[0]["body"] == {"texts": ["a"], "input_type": "search_query", "truncate": "NONE"}


async def test_bedrock_records_input_tokens_from_the_response_header():
    client = BedrockEmbeddingClient(
        _FakeBedrockRuntime(_v4_payload, input_tokens=9),
        model="cohere.embed-v4:0",
        embedding_format=CohereEmbedV4Format(),
        recorder=UsageRecorder(),
    )

    with usage_scope() as scope, call_purpose("billing_codes.retrieval"):
        await client.embed_query("a")

    [call] = scope.records
    assert (call.kind, call.provider, call.model) == ("embedding", "bedrock", "cohere.embed-v4:0")
    assert call.purpose == "billing_codes.retrieval"
    assert (call.input_tokens, call.output_tokens) == (9, None)


async def test_bedrock_raises_and_records_a_short_answer():
    client = BedrockEmbeddingClient(
        _FakeBedrockRuntime(lambda body: {"embeddings": {"float": []}}),
        model="cohere.embed-v4:0",
        embedding_format=CohereEmbedV4Format(),
        recorder=UsageRecorder(),
    )

    with usage_scope() as scope, pytest.raises(RuntimeError, match="0 vectors for 1 texts"):
        await client.embed(["a"])
    assert "0 vectors" in scope.records[0].error


async def test_bedrock_embed_of_nothing_makes_no_call():
    runtime = _FakeBedrockRuntime(_v4_payload)
    client = BedrockEmbeddingClient(runtime, model="cohere.embed-v4:0", embedding_format=CohereEmbedV4Format())

    assert await client.embed([]) == []
    assert runtime.requests == []


# -- startup model guard -------------------------------------------------------------------


async def _table(tmp_path, name: str, dimension: int, *, embedding_model: str | None = None):
    connection = await lancedb.connect_async(str(tmp_path))
    schema = pa.schema(
        [pa.field("id", pa.string()), pa.field("vector", pa.list_(pa.float32(), dimension))],
        metadata={"embedding_model": embedding_model} if embedding_model else None,
    )
    return await connection.create_table(name, schema=schema)


def _query_client(dimension: int, identity: str = "mistral:mistral-embed") -> FakeEmbeddingClient:
    provider, _, model = identity.partition(":")
    return FakeEmbeddingClient(default=[0.0] * dimension, provider_name=provider, model_name=model)


async def test_stored_embedding_reads_the_width_and_the_recorded_model(tmp_path):
    table = await _table(tmp_path, "codes_test", 1024, embedding_model="bedrock:cohere.embed-v4:0")
    assert await stored_embedding(table) == StoredEmbedding(1024, "bedrock:cohere.embed-v4:0")


async def test_stored_embedding_of_a_table_recording_no_model(tmp_path):
    table = await _table(tmp_path, "documents-embeddings", 1024)
    assert await stored_embedding(table) == StoredEmbedding(1024, None)


async def test_guard_passes_when_every_table_matches():
    await EmbeddingModelGuard(_query_client(1024)).check({
        "codes_test": StoredEmbedding(1024, "mistral:mistral-embed"),
        # A table recording no model was built with mistral-embed.
        "documents-embeddings": StoredEmbedding(1024, None),
    })


async def test_guard_passes_a_bedrock_client_on_its_own_table():
    await EmbeddingModelGuard(_query_client(1024, "bedrock:cohere.embed-v4:0")).check(
        {"codes_test__embed-v4:0": StoredEmbedding(1024, "bedrock:cohere.embed-v4:0")}
    )


async def test_guard_raises_on_another_model_of_the_same_width():
    # Cohere v4 at 1024 dims has mistral-embed's width: only the recorded name tells them apart.
    guard = EmbeddingModelGuard(_query_client(1024, "bedrock:cohere.embed-v4:0"))
    with pytest.raises(EmbeddingModelMismatchError) as excinfo:
        await guard.check({
            "codes_legacy": StoredEmbedding(1024, None),
            "codes_variant": StoredEmbedding(1024, "bedrock:cohere.embed-v4:0"),
        })
    message = str(excinfo.value)
    assert "'bedrock:cohere.embed-v4:0'" in message
    assert "codes_legacy (mistral:mistral-embed, dim 1024)" in message
    assert "codes_variant" not in message


async def test_guard_raises_naming_the_model_and_the_mismatched_dimension():
    guard = EmbeddingModelGuard(_query_client(768, "mistral:mistral-embed"))
    with pytest.raises(EmbeddingModelMismatchError) as excinfo:
        await guard.check({"codes_test": StoredEmbedding(1024, "mistral:mistral-embed")})
    message = str(excinfo.value)
    assert "768-dim" in message and "codes_test (mistral:mistral-embed, dim 1024)" in message
