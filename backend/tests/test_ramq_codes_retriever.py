"""Unit tests for RAMQCodesRetriever/candidates_from_nodes (app/ramq_codes/retriever.py),
against a small in-memory llama_index vector store built with a deterministic fake
embedding model (exact text->vector lookup, no network call, no real Mistral API key
needed). Mirrors the retrieval-mechanics style of the old tests/test_vector_retrieval.py
(deleted in the "vector retrieval pattern change" commit, cc787b5) but pinned to the
current RAMQCodesRetriever/candidates_from_nodes interface — nothing exercised the real
candidate-building path at all between that deletion and this file.

Known gap this file documents rather than hides: the current implementation applies no
relevance floor and no per-code dedup (see root README's "How it's extensible" section) —
a prior MIN_SIMILARITY cosine-similarity floor + dedup existed on the old retriever and
were dropped when this module was rewritten, without being reinstated.
test_retrieve_returns_low_similarity_hits_unfiltered below pins that current (gap)
behavior explicitly, so reinstating a floor is a visible, intentional test change rather
than an unnoticed regression the way the removal itself was.
"""

from typing import Any, Optional

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import BaseNode, NodeWithScore, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.core.bridge.pydantic import PrivateAttr
import pytest

from app.ramq_codes.retriever import RAMQCodesRetriever, candidates_from_nodes


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeVectorStore(BasePydanticVectorStore):
    """In-memory stand-in for the real LanceDBVectorStore: stores nodes directly (with
    precomputed .embedding vectors) and answers query() with plain cosine similarity, so
    RAMQCodesRetriever's VectorStoreIndex.from_vector_store(...).as_retriever() has
    something real to search without a Lance dataset or embedding API call."""

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


def _node(code: str, text: str, metadata: dict | None = None) -> TextNode:
    full_metadata = {"number": code, **(metadata or {})}
    node = TextNode(text=text, metadata=full_metadata)
    node.embedding = None  # set by caller via vectors lookup below
    return node


def _retriever(vectors: dict[str, list[float]], nodes: list[TextNode]) -> RAMQCodesRetriever:
    for node in nodes:
        node.embedding = vectors[node.text]
    return RAMQCodesRetriever(_FakeVectorStore(nodes), _LookupEmbedding(vectors))


def test_retrieve_ranks_best_semantic_match_first():
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    retriever = _retriever(vectors, [_node("CHAT", "chat"), _node("CHIEN", "chien"), _node("AVION", "avion")])

    results = candidates_from_nodes(retriever.retrieve("query"))

    assert [c.code for c in results][:2] == ["CHAT", "CHIEN"]


def test_retrieve_caps_results_at_thirty():
    vectors = {f"code {i}": [1.0, float(i)] for i in range(35)}
    vectors["query"] = [1.0, 0.0]
    nodes = [_node(str(i), f"code {i}") for i in range(35)]

    retriever = _retriever(vectors, nodes)
    results = retriever.retrieve("query")

    assert len(results) == 30


def test_retrieve_returns_low_similarity_hits_unfiltered():
    # Documents a known gap (see module docstring): an orthogonal/unrelated query still
    # comes back with a candidate today, because no MIN_SIMILARITY-style floor is applied
    # here anymore. If a floor is reinstated, this assertion is expected to flip.
    vectors = {"a": [1.0, 0.0], "query": [0.0, 1.0]}
    retriever = _retriever(vectors, [_node("A", "a")])

    results = candidates_from_nodes(retriever.retrieve("query"))

    assert [c.code for c in results] == ["A"]


def test_candidates_from_nodes_builds_candidate_from_full_metadata():
    metadata = {
        "number": "15801",
        "description": "Visite de prise en charge",
        "when_to_use": ["Nouveau patient"],
        "rules": ["Clientele < 500 patients inscrits"],
        "fees": [{"amount": 33.15, "when_to_use": "Par visite", "majoration": None}],
    }
    hit = NodeWithScore(node=TextNode(text="", metadata=metadata), score=0.9)

    (candidate,) = candidates_from_nodes([hit])

    assert candidate.code == "15801"
    assert candidate.description == "Visite de prise en charge"
    assert candidate.when_to_use == ("Nouveau patient",)
    assert candidate.rules == ("Clientele < 500 patients inscrits",)
    assert candidate.fees[0].amount == 33.15
    assert candidate.fees[0].when_to_use == "Par visite"


def test_candidates_from_nodes_defaults_missing_optional_fields():
    hit = NodeWithScore(node=TextNode(text="", metadata={"number": "15801"}), score=0.9)

    (candidate,) = candidates_from_nodes([hit])

    assert candidate.description == ""
    assert candidate.when_to_use == ()
    assert candidate.rules == ()
    assert candidate.fees == ()


def test_candidates_from_nodes_drops_hits_without_a_number():
    with_number = NodeWithScore(node=TextNode(text="", metadata={"number": "15801"}), score=0.9)
    without_number = NodeWithScore(node=TextNode(text="", metadata={"description": "no code here"}), score=0.9)

    results = candidates_from_nodes([without_number, with_number])

    assert [c.code for c in results] == ["15801"]


@pytest.mark.parametrize("bad_metadata", [{"number": ""}, {"number": None}])
def test_candidates_from_nodes_treats_empty_number_as_missing(bad_metadata):
    hit = NodeWithScore(node=TextNode(text="", metadata=bad_metadata), score=0.9)

    assert candidates_from_nodes([hit]) == []
