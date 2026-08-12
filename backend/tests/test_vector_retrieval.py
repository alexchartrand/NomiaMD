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


def _node(code: str, text: str, metadata: dict | None = None) -> TextNode:
    # excluded_embed_metadata_keys: get_content(MetadataMode.EMBED) otherwise prepends the
    # metadata dict onto the node text, which would mean embedding more than just `text` the
    # vectors lookup dict is keyed on.
    full_metadata = {"number": code, **(metadata or {})}
    return TextNode(text=text, metadata=full_metadata, excluded_embed_metadata_keys=list(full_metadata))


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
    results = [c.code for c in retriever.candidates_for("query", limit=3)]
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
    assert [c.code for c in retriever.candidates_for("query", limit=5)] == ["A"]


def test_candidates_for_reads_description_when_to_use_and_rules_from_node_metadata():
    metadata = {
        "description": "Description du code A",
        "when_to_use": ["Scénario A"],
        "rules": ["Règle A"],
    }
    vectors = {"a": [1.0, 0.0], "query": [1.0, 0.0]}
    retriever = _retriever(vectors, [_node("A", "a", metadata)])
    [candidate] = retriever.candidates_for("query", limit=5)
    assert candidate.description == "Description du code A"
    assert candidate.when_to_use == ("Scénario A",)
    assert candidate.rules == ("Règle A",)


def test_candidates_for_reads_fees_from_node_metadata():
    metadata = {
        "description": "Description du code A",
        "fees": [
            {"amount": 27.25, "when_to_use": "En cabinet", "majoration": None},
            {"amount": 15.5, "when_to_use": "En soirée", "majoration": "Applicable en vertu de l'annexe X"},
        ],
    }
    vectors = {"a": [1.0, 0.0], "query": [1.0, 0.0]}
    retriever = _retriever(vectors, [_node("A", "a", metadata)])
    [candidate] = retriever.candidates_for("query", limit=5)
    assert [f.amount for f in candidate.fees] == [27.25, 15.5]
    assert candidate.fees[0].when_to_use == "En cabinet"
    assert candidate.fees[0].majoration is None
    assert candidate.fees[1].majoration == "Applicable en vertu de l'annexe X"


def test_candidates_for_defaults_to_no_fees_when_metadata_omits_them():
    vectors = {"a": [1.0, 0.0], "query": [1.0, 0.0]}
    retriever = _retriever(vectors, [_node("A", "a", {"description": "Description du code A"})])
    [candidate] = retriever.candidates_for("query", limit=5)
    assert candidate.fees == ()
