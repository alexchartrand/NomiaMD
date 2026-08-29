"""Unit tests for RAMQCodesRetriever (app/ramq_codes/retriever.py).

RAMQCodesRetriever is exercised against a fake ICodeRepository (standing in for the real
CodeRepository/`codes` LanceDB table) and a deterministic fake embedding model (exact
text->vector lookup, no network call, no real Mistral API key needed). Real hybrid-search
ranking behavior (vector+FTS fusion, relevance scoring) is LanceDB's own job and is pinned
against a real lancedb table in tests/test_lancedb_code_repository.py instead — this file
only pins RAMQCodesRetriever's own responsibilities: embed the query, call hybrid_search
with it, convert each hit via the injected converter, in order. Unlike the old
code-embeddings-backed retriever, a hit already carries the full row — there's no separate
hydrate-by-number join for BillingCodesTask to make any more (see tests/test_ramq_codes_task.py)."""

from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.lancedb.models import CodeRow
from app.ramq_codes.models import Code
from app.ramq_codes.retriever import RAMQCodesRetriever


class _FakeCodeRepository:
    def __init__(self, hits: list[tuple[CodeRow, float]]):
        self._hits = hits
        self.last_call: dict[str, Any] | None = None

    async def hybrid_search(self, text: str, vector: list[float], k: int) -> list[tuple[CodeRow, float]]:
        self.last_call = {"text": text, "vector": vector, "k": k}
        return self._hits


class _LookupEmbedding(BaseEmbedding):
    """Exact text->vector lookup, standing in for a real embedding model in tests."""

    vectors: dict[str, list[float]]

    def __init__(self, vectors: dict[str, list[float]], **kwargs: Any):
        super().__init__(vectors=vectors, **kwargs)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self.vectors[query]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self.vectors[query]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self.vectors[text]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self.vectors[text]


class _FakeConverter:
    def convert(self, data: CodeRow) -> Code:
        return Code(number=data.number, libelle=data.libelle, description=data.description)


def _row(number: str) -> CodeRow:
    return CodeRow(number=number, libelle=f"libelle {number}", description=f"description {number}")


async def test_aretrieve_embeds_the_query_and_passes_the_vector_to_hybrid_search():
    codes = _FakeCodeRepository([(_row("A"), 0.9)])
    embed_model = _LookupEmbedding({"query": [1.0, 0.0]})
    retriever = RAMQCodesRetriever(codes, embed_model, _FakeConverter())

    await retriever.aretrieve("query")

    assert codes.last_call == {"text": "query", "vector": [1.0, 0.0], "k": 20}


async def test_aretrieve_converts_every_hit_via_the_injected_converter_in_order():
    codes = _FakeCodeRepository([(_row("A"), 0.9), (_row("B"), 0.5)])
    embed_model = _LookupEmbedding({"query": [1.0, 0.0]})
    retriever = RAMQCodesRetriever(codes, embed_model, _FakeConverter())

    candidates = await retriever.aretrieve("query")

    assert [c.number for c in candidates] == ["A", "B"]


async def test_aretrieve_returns_empty_list_when_no_hits():
    codes = _FakeCodeRepository([])
    embed_model = _LookupEmbedding({"query": [1.0, 0.0]})
    retriever = RAMQCodesRetriever(codes, embed_model, _FakeConverter())

    assert await retriever.aretrieve("query") == []


async def test_aretrieve_respects_a_custom_similarity_top_k():
    codes = _FakeCodeRepository([])
    embed_model = _LookupEmbedding({"query": [1.0, 0.0]})
    retriever = RAMQCodesRetriever(codes, embed_model, _FakeConverter(), similarity_top_k=5)

    await retriever.aretrieve("query")

    assert codes.last_call["k"] == 5
