"""Unit tests for RAMQCodesRetriever (app/ramq_codes/retriever.py).

RAMQCodesRetriever is exercised against a small in-memory llama_index vector store
(`_FakeVectorStore`, standing in for the real `code-embeddings` LanceDB table) built with a
deterministic fake embedding model (exact text->vector lookup, no network call, no real
Mistral API key needed). RAMQCodesRetriever itself does no joining against the `codes` table
— it only surfaces candidate `number`s off `code-embeddings` node metadata; task.py
(BillingCodesTask) is what joins those numbers against full row data via CodesData/
CodesData's ICodeRepository, see tests/test_ramq_codes_codes_data.py for that.

The retriever fuses a vector retriever with a BM25Retriever (QueryFusionRetriever, mode=
"relative_score", num_queries=1 so no LLM-generated query variants — just the raw query
against both). `num_queries=1` means the llm is never actually invoked, but
QueryFusionRetriever still resolves one at construction time regardless (see
app/ramq_codes/factory.py's docstring), so tests pass a MockLLM — cheap, deterministic,
no API key — as a stand-in for the real Mistral llm.

Known gap this file documents rather than hides: the current implementation applies no
relevance floor and no per-code dedup (see CLAUDE.md's Architecture section) — a prior
MIN_SIMILARITY cosine-similarity floor existed on an earlier retriever rewrite and hasn't
been reinstated. test_retrieve_returns_low_similarity_hits_unfiltered below pins that
current (gap) behavior explicitly, so reinstating a floor is a visible, intentional test
change rather than an unnoticed regression the way the removal itself was.
"""

from typing import Any, Optional

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.llms.mock import MockLLM

from app.ramq_codes.retriever import RAMQCodesRetriever


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeVectorStore(BasePydanticVectorStore):
    """In-memory stand-in for the real `code-embeddings` LanceDBVectorStore: stores nodes
    directly (with precomputed .embedding vectors) and answers query() with plain cosine
    similarity, so RAMQCodesRetriever's VectorStoreIndex.from_vector_store(...).as_retriever()
    has something real to search without a Lance dataset or embedding API call."""

    stores_text: bool = True
    _nodes: list[BaseNode] = PrivateAttr(default_factory=list)

    def __init__(self, nodes: list[BaseNode]):
        super().__init__()
        self._nodes = list(nodes)

    @property
    def client(self) -> None:
        return None

    def add(self, nodes: list[BaseNode], **kwargs: Any) -> list[str]:
        self._nodes.extend(nodes)
        return [n.node_id for n in nodes]

    def delete(self, ref_doc_id: str, **kwargs: Any) -> None:
        self._nodes = [n for n in self._nodes if n.ref_doc_id != ref_doc_id]

    def get_nodes(self, node_ids: Optional[list[str]] = None, filters: Any = None) -> list[BaseNode]:
        return list(self._nodes)

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        scored = sorted(
            ((n, _cosine(query.query_embedding, n.embedding)) for n in self._nodes),
            key=lambda pair: pair[1],
            reverse=True,
        )
        top = scored[: query.similarity_top_k]
        return VectorStoreQueryResult(
            nodes=[n for n, _ in top],
            similarities=[s for _, s in top],
            ids=[n.node_id for n, _ in top],
        )


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


def _embedding_node(code: str, text: str) -> TextNode:
    # code-embeddings' node metadata carries only `number` (see ramq-ingestion's
    # src/embedding/code_node_builder.py).
    return TextNode(text=text, metadata={"number": code})


def _retriever(
    vectors: dict[str, list[float]], embedding_nodes: list[TextNode], **kwargs: Any
) -> RAMQCodesRetriever:
    for node in embedding_nodes:
        node.embedding = vectors[node.text]
    return RAMQCodesRetriever(
        _FakeVectorStore(embedding_nodes), _LookupEmbedding(vectors), MockLLM(), **kwargs
    )


def _numbers(retriever: RAMQCodesRetriever, query: str) -> list[str]:
    return [hit.node.metadata.get("number") for hit in retriever.retrieve(query)]


async def test_aretrieve_delegates_to_the_inner_retriever_like_retrieve_does():
    # BillingCodesTask.build_prompt calls .aretrieve(), not .retrieve() — pin that the
    # async path (RAMQCodesRetriever._aretrieve) actually delegates to the inner
    # VectorIndexRetriever's own .aretrieve() rather than silently falling back to
    # BaseRetriever's default (which just runs the sync path under an async wrapper).
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    embedding_nodes = [_embedding_node("CHAT", "chat"), _embedding_node("CHIEN", "chien"), _embedding_node("AVION", "avion")]
    retriever = _retriever(vectors, embedding_nodes)

    hits = await retriever.aretrieve("query")

    assert [hit.node.metadata.get("number") for hit in hits][:2] == ["CHAT", "CHIEN"]


def test_retrieve_ranks_best_semantic_match_first():
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    embedding_nodes = [_embedding_node("CHAT", "chat"), _embedding_node("CHIEN", "chien"), _embedding_node("AVION", "avion")]
    retriever = _retriever(vectors, embedding_nodes)

    assert _numbers(retriever, "query")[:2] == ["CHAT", "CHIEN"]


def test_retrieve_caps_results_at_similarity_top_k_of_20():
    # Both the vector and BM25 legs, and the fusion itself, are hardcoded to
    # similarity_top_k=20 (app/ramq_codes/retriever.py) — no longer a constructor param.
    vectors = {f"code {i}": [1.0, float(i)] for i in range(35)}
    vectors["query"] = [1.0, 0.0]
    embedding_nodes = [_embedding_node(str(i), f"code {i}") for i in range(35)]

    retriever = _retriever(vectors, embedding_nodes)

    assert len(retriever.retrieve("query")) == 20


def test_retrieve_returns_low_similarity_hits_unfiltered():
    # Documents a known gap (see module docstring): an orthogonal/unrelated query still
    # comes back with a candidate today, because no MIN_SIMILARITY-style floor is applied
    # here. If a floor is reinstated, this assertion is expected to flip.
    vectors = {"a": [1.0, 0.0], "query": [0.0, 1.0]}
    retriever = _retriever(vectors, [_embedding_node("A", "a")])

    assert _numbers(retriever, "query") == ["A"]


def test_retrieve_hit_metadata_carries_only_the_code_number():
    # task.py (BillingCodesTask.build_prompt) reads nothing off retriever hits besides
    # metadata["number"] — pin that this is genuinely all a code-embeddings hit carries,
    # rather than accidentally depending on richer node data that only test fakes provide.
    vectors = {"a": [1.0, 0.0], "query": [1.0, 0.0]}
    retriever = _retriever(vectors, [_embedding_node("15801", "a")])

    (hit,) = retriever.retrieve("query")

    assert hit.node.metadata == {"number": "15801"}
