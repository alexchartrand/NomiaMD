"""Unit tests for RAMQCodesRetriever/candidates_from_nodes (app/ramq_codes/retriever.py),
against a small in-memory lancedb-table stand-in built with a deterministic fake embedding
model (exact text->vector lookup, no network call, no real Mistral API key needed).

Known gap this file documents rather than hides: the current implementation applies no
relevance floor and no per-code dedup (see root README's "How it's extensible" section) —
a prior MIN_SIMILARITY cosine-similarity floor + dedup existed on the old retriever and
were dropped when this module was rewritten, without being reinstated.
test_retrieve_returns_low_similarity_hits_unfiltered below pins that current (gap)
behavior explicitly, so reinstating a floor is a visible, intentional test change rather
than an unnoticed regression the way the removal itself was.
"""

from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import NodeWithScore, TextNode
import pytest

from app.ramq_codes.retriever import RAMQCodesRetriever, candidates_from_nodes


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeSearchQuery:
    """Chainable stand-in for lancedb's query builder: .distance_type(...).limit(k).to_list()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._limit: int | None = None

    def distance_type(self, name: str) -> "_FakeSearchQuery":
        return self

    def limit(self, k: int) -> "_FakeSearchQuery":
        self._limit = k
        return self

    def to_list(self) -> list[dict]:
        return self._rows[: self._limit] if self._limit is not None else self._rows


class _FakeTable:
    """In-memory stand-in for a real lancedb Table: stores rows directly (each a dict with
    a "vector" key) and answers .search(vector) with plain cosine-distance ranking, so
    RAMQCodesRetriever has something real to search without an actual Lance dataset."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def search(self, query_vector: list[float]) -> _FakeSearchQuery:
        scored = sorted(
            ({**row, "_distance": 1 - _cosine(query_vector, row["vector"])} for row in self._rows),
            key=lambda row: row["_distance"],
        )
        return _FakeSearchQuery(scored)


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


def _row(code: str, text: str, vectors: dict[str, list[float]], metadata: dict | None = None) -> dict:
    return {"number": code, "text": text, "vector": vectors[text], **(metadata or {})}


def _retriever(vectors: dict[str, list[float]], rows: list[dict]) -> RAMQCodesRetriever:
    return RAMQCodesRetriever(_FakeTable(rows), _LookupEmbedding(vectors))


def test_retrieve_ranks_best_semantic_match_first():
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    rows = [_row("CHAT", "chat", vectors), _row("CHIEN", "chien", vectors), _row("AVION", "avion", vectors)]
    retriever = _retriever(vectors, rows)

    results = candidates_from_nodes(retriever.retrieve("query"))

    assert [c.code for c in results][:2] == ["CHAT", "CHIEN"]


def test_retrieve_caps_results_at_similarity_top_k():
    vectors = {f"code {i}": [1.0, float(i)] for i in range(35)}
    vectors["query"] = [1.0, 0.0]
    rows = [_row(str(i), f"code {i}", vectors) for i in range(35)]

    retriever = _retriever(vectors, rows)
    results = retriever.retrieve("query")

    assert len(results) == 20


def test_retrieve_returns_low_similarity_hits_unfiltered():
    # Documents a known gap (see module docstring): an orthogonal/unrelated query still
    # comes back with a candidate today, because no MIN_SIMILARITY-style floor is applied
    # here anymore. If a floor is reinstated, this assertion is expected to flip.
    vectors = {"a": [1.0, 0.0], "query": [0.0, 1.0]}
    retriever = _retriever(vectors, [_row("A", "a", vectors)])

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


def test_retrieve_wraps_rows_as_nodes_with_metadata_matching_row_fields():
    vectors = {"a": [1.0, 0.0], "query": [1.0, 0.0]}
    row = _row("15801", "a", vectors, metadata={"description": "d", "when_to_use": ["x"]})
    retriever = _retriever(vectors, [row])

    (hit,) = retriever.retrieve("query")

    assert hit.node.metadata["number"] == "15801"
    assert hit.node.metadata["description"] == "d"
    assert hit.node.metadata["when_to_use"] == ["x"]
    assert hit.node.text == "a"
