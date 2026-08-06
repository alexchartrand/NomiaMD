"""Unit tests for RamqVectorRetriever against a small in-memory llama_index VectorStoreIndex
built with a deterministic fake embedding model (exact text->vector lookup, no network call,
no real Mistral API key needed)."""

from typing import Any

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import TextNode

from app.ramq.vector_retrieval import RamqVectorRetriever


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


def _retriever(vectors: dict[str, list[float]], nodes: list[TextNode]) -> RamqVectorRetriever:
    index = VectorStoreIndex(nodes, embed_model=_LookupEmbedding(vectors))
    return RamqVectorRetriever(index)


def _node(code: str, text: str) -> TextNode:
    # excluded_embed_metadata_keys: get_content(MetadataMode.EMBED) otherwise prepends
    # "number: <code>\n\n" to the node text, which would mean embedding "number: A\n\na"
    # instead of the plain "a" the vectors lookup dict is keyed on.
    return TextNode(text=text, metadata={"number": code}, excluded_embed_metadata_keys=["number"])


def test_candidates_ranked_by_cosine_similarity():
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    retriever = _retriever(
        vectors,
        [_node("CHAT", "chat"), _node("CHIEN", "chien"), _node("AVION", "avion")],
    )
    results = retriever.candidates_for("query", limit=3)
    assert results[0] == "CHAT"
    assert results[1] == "CHIEN"
    assert "AVION" not in results  # orthogonal vector -> similarity ~0, below MIN_SIMILARITY


def test_candidates_for_respects_limit():
    vectors = {
        "a": [1.0, 0.0],
        "b": [0.95, 0.05],
        "c": [0.9, 0.1],
        "query": [1.0, 0.0],
    }
    retriever = _retriever(vectors, [_node("A", "a"), _node("B", "b"), _node("C", "c")])
    assert len(retriever.candidates_for("query", limit=2)) == 2


def test_candidates_for_applies_minimum_similarity_floor():
    # An unrelated query should yield [] rather than "whichever nodes ranked least badly" —
    # a low, roughly-orthogonal similarity score must be filtered out entirely.
    vectors = {"a": [1.0, 0.0], "query": [0.0, 1.0]}
    retriever = _retriever(vectors, [_node("A", "a")])
    assert retriever.candidates_for("query", limit=5) == []


def test_candidates_for_dedupes_and_drops_nodes_without_a_number():
    vectors = {"a": [1.0, 0.0], "a-dup": [1.0, 0.0], "query": [1.0, 0.0]}
    nodes = [
        _node("A", "a"),
        _node("A", "a-dup"),  # same code, different node
        TextNode(text="a", metadata={}),  # no "number" metadata at all
    ]
    retriever = _retriever(vectors, nodes)
    assert retriever.candidates_for("query", limit=5) == ["A"]
