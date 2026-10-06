"""app/llm/embeddings.py's provider selection from EMBEDDING_PROVIDER, and the startup
dimension guard (app/llm/embedding_guard.py) against real temp LanceDB tables' vector
columns. Builds real llama-index clients (no network — construction doesn't call out); the
guard's probe goes through a fixed-dimension fake embedding model."""

import lancedb
import pyarrow as pa
import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.mistralai import MistralAIEmbedding
from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from app.lancedb.database import vector_dimension
from app.llm import (
    EmbeddingDimensionGuard,
    EmbeddingDimensionMismatchError,
    UnknownEmbeddingProviderError,
    embedding_provider,
    get_embedding_model,
)
from app.llm.mistral import MistralEmbeddingProvider
from app.llm.openai_compatible import OpenAICompatibleEmbeddingProvider


@pytest.fixture(autouse=True)
def fresh_embedding_cache():
    get_embedding_model.cache_clear()
    yield
    get_embedding_model.cache_clear()


def test_defaults_to_mistral(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "mistral-embed")
    assert isinstance(embedding_provider(), MistralEmbeddingProvider)
    model = get_embedding_model()
    assert isinstance(model, MistralAIEmbedding)
    assert model.model_name == "mistral-embed"


def test_selects_openai_compatible(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8081/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    assert isinstance(embedding_provider(), OpenAICompatibleEmbeddingProvider)
    model = get_embedding_model()
    assert isinstance(model, OpenAILikeEmbedding)
    assert model.api_base == "http://localhost:8081/v1"
    assert model.model_name == "BAAI/bge-m3"


@pytest.mark.parametrize("missing", ["EMBEDDING_API_KEY", "EMBEDDING_MODEL"])
def test_mistral_requires_key_and_model(monkeypatch, missing):
    # Not the SDK's own MISTRAL_API_KEY fallback: a missing role-based key fails loudly.
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "mistral-embed")
    monkeypatch.setenv("MISTRAL_API_KEY", "sdk-fallback-key")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY.*EMBEDDING_MODEL"):
        get_embedding_model()


@pytest.mark.parametrize("missing", ["EMBEDDING_ENDPOINT", "EMBEDDING_MODEL"])
def test_openai_compatible_requires_endpoint_and_model(monkeypatch, missing):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8081/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="EMBEDDING_ENDPOINT.*EMBEDDING_MODEL"):
        get_embedding_model()


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


class _FixedDimensionEmbedding(BaseEmbedding):
    dimension: int

    def _vector(self) -> list[float]:
        return [0.0] * self.dimension

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vector()

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vector()

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._vector()


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
    guard = EmbeddingDimensionGuard(_FixedDimensionEmbedding(dimension=8, model_name="fake"))
    await guard.check({
        "codes_test": await vector_dimension(codes),
        "documents-embeddings": await vector_dimension(documents),
    })


async def test_guard_raises_naming_the_model_and_the_mismatched_table(tmp_path):
    codes = await _table_with_vector_dimension(tmp_path, "codes_test", 1024)
    documents = await _table_with_vector_dimension(tmp_path, "documents-embeddings", 768)
    guard = EmbeddingDimensionGuard(_FixedDimensionEmbedding(dimension=768, model_name="bge-local"))
    with pytest.raises(EmbeddingDimensionMismatchError) as excinfo:
        await guard.check({
            "codes_test": await vector_dimension(codes),
            "documents-embeddings": await vector_dimension(documents),
        })
    message = str(excinfo.value)
    assert "'bge-local'" in message and "768-dim" in message
    assert "codes_test (dim 1024)" in message
    assert "documents-embeddings" not in message
