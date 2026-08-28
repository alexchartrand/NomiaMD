"""Unit tests for RAMQManualRetriever (app/ramq_chatbot/retriever.py) — hybrid (vector+FTS)
search fanned out across IQueryGenerator's generated queries and RRF-fused via
ReciprocalRankFuser, over `IDocumentRepository`.

No network calls / real API keys: DocumentRepository is an in-memory fake whose
hybrid_search ranks by cosine similarity against precomputed row vectors (real FTS/RRF
fusion-within-a-query is LanceDB's own job — see tests/test_lancedb_document_repository.py —
not something this retriever does or needs to fake); the injected embed_model is a
deterministic exact-text-lookup fake (mirrors tests/test_vector_retrieval.py's
_LookupEmbedding). Query generation (test_ramq_chatbot_query_generator.py) and RRF fusion
(test_ramq_chatbot_fusion.py) have their own dedicated unit tests — most tests here use a
single-query IQueryGenerator stand-in so they aren't incidentally testing fan-out too."""

from typing import Any, List, Tuple

import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import NodeWithScore

from app.lancedb.converter import CodesRowConverter, DocumentRowConverter
from app.lancedb.models import DocumentRow
from app.lancedb.repository import ICodeRepository, IDocumentRepository
from app.ramq_chatbot.fusion import ReciprocalRankFuser
from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.query_generator import IQueryGenerator
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeDocumentRepository(IDocumentRepository):
    """In-memory stand-in for DocumentRepository: hybrid_search ranks rows by cosine
    similarity between the query vector and each row's own precomputed vector (looked up by
    its text, mirroring TextNode.embedding in the old vector-store-based fixtures) —
    RAMQManualRetriever's own job is fanning out + RRF-fusing across queries, not per-query
    ranking, which real DocumentRepository/LanceDB already owns."""

    def __init__(self, rows: list[DocumentRow], vectors: dict[str, list[float]]):
        self._rows = rows
        self._vectors = vectors
        self.hybrid_search_calls: list[tuple[str, list[float], int]] = []

    async def get_by_section_number(self, section_number: str) -> list[DocumentRow]:
        return [r for r in self._rows if r.section_number == section_number]

    async def get_by_code_reference(self, code: str) -> list[DocumentRow]:
        raise NotImplementedError

    async def hybrid_search(
        self, text: str, vector: list[float], k: int
    ) -> List[Tuple[DocumentRow, float]]:
        self.hybrid_search_calls.append((text, vector, k))
        scored = sorted(
            ((row, _cosine(vector, self._vectors[row.text])) for row in self._rows),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return list(scored[:k])


class _LookupEmbedding(BaseEmbedding):
    """Exact text->vector lookup, passed as RAMQManualRetriever's embed_model."""

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


class _SingleQueryGenerator(IQueryGenerator):
    """Fan-out-free stand-in: always returns exactly the original query untouched, no LLM
    call — keeps ranking/reference-expansion tests from needing query-fan-out fixtures
    they aren't about."""

    async def agenerate(self, query: str, num_queries: int) -> list[str]:
        return [query]


class _SpyQueryGenerator(IQueryGenerator):
    def __init__(self, queries_by_input: dict[str, list[str]]):
        self._queries_by_input = queries_by_input
        self.calls: list[tuple[str, int]] = []

    async def agenerate(self, query: str, num_queries: int) -> list[str]:
        self.calls.append((query, num_queries))
        return self._queries_by_input[query]


class _NoOpReferenceExpander:
    async def aexpand(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        return nodes


class _EmptyCodesTableReader(ICodeRepository):
    async def get_by_number(self, number: str):
        raise NotImplementedError

    async def list_by_numbers(self, numbers: list[str]) -> list:
        return []


def _row(row_id: str, text: str, metadata: dict | None = None) -> DocumentRow:
    metadata = metadata or {}
    return DocumentRow(
        id=row_id,
        text=text,
        title="Guide",
        section_number=metadata.get("section_number"),
        section_references=metadata.get("section_references"),
        code_references=metadata.get("code_references"),
    )


def _build_retriever(
    vectors: dict[str, list[float]],
    rows: list[DocumentRow],
    query_generator: IQueryGenerator | None = None,
    reference_expander=None,
    similarity_top_k: int = 20,
) -> tuple[RAMQManualRetriever, _FakeDocumentRepository]:
    documents = _FakeDocumentRepository(rows, vectors)
    retriever = RAMQManualRetriever(
        documents=documents,
        embed_model=_LookupEmbedding(vectors),
        query_generator=query_generator or _SingleQueryGenerator(),
        fuser=ReciprocalRankFuser(),
        converter=DocumentRowConverter(),
        reference_expander=reference_expander or _NoOpReferenceExpander(),
        similarity_top_k=similarity_top_k,
    )
    return retriever, documents


def _build_reference_expander(rows: list[DocumentRow], vectors: dict[str, list[float]]) -> ReferenceExpander:
    documents = _FakeDocumentRepository(rows, vectors)
    return ReferenceExpander(
        section_lookup=ManualSectionLookup(documents, DocumentRowConverter()),
        codes_data=CodesData(_EmptyCodesTableReader(), CodesRowConverter()),
    )


def test_retrieve_raises_not_implemented():
    # RAMQManualRetriever is async-only — IDocumentRepository has no sync query path.
    retriever, _ = _build_retriever({}, [])

    with pytest.raises(NotImplementedError):
        retriever.retrieve("urgence de nuit")


async def test_aretrieve_ranks_best_match_first():
    vectors = {
        "urgence de nuit": [1.0, 0.0],
        "consultation de routine": [0.0, 1.0],
    }
    row_a = _row("A", "urgence de nuit")
    row_b = _row("B", "consultation de routine")

    retriever, _ = _build_retriever(vectors, [row_a, row_b])
    results = await retriever.aretrieve("urgence de nuit")

    assert results[0].node.node_id == "A"


async def test_empty_table_returns_no_hits():
    # Current behavior, and a design goal this time (unlike the old BM25-backed retriever,
    # which raised outright on an empty corpus): DocumentRepository.hybrid_search on an
    # empty table just returns [], so aretrieve degrades gracefully instead of crashing.
    retriever, _ = _build_retriever({"urgence de nuit": [1.0, 0.0]}, [])

    assert await retriever.aretrieve("urgence de nuit") == []


async def test_aretrieve_passes_similarity_top_k_through_to_hybrid_search():
    vectors = {f"code {i}": [1.0, float(i)] for i in range(22)}
    rows = [_row(str(i), f"code {i}") for i in range(22)]

    retriever, documents = _build_retriever(vectors, rows)
    results = await retriever.aretrieve("code 0")

    assert len(results) <= 20
    assert documents.hybrid_search_calls[0][2] == 20


async def test_aretrieve_calls_hybrid_search_once_per_generated_query():
    vectors = {"original": [1.0, 0.0], "generated": [0.0, 1.0]}
    rows = [_row("A", "original")]
    query_generator = _SpyQueryGenerator({"original": ["original", "generated"]})

    retriever, documents = _build_retriever(vectors, rows, query_generator=query_generator)
    await retriever.aretrieve("original")

    assert query_generator.calls == [("original", 3)]  # default num_queries=3
    assert [call[0] for call in documents.hybrid_search_calls] == ["original", "generated"]
    assert documents.hybrid_search_calls[0][1] == vectors["original"]
    assert documents.hybrid_search_calls[1][1] == vectors["generated"]


async def test_aretrieve_delegates_final_nodes_to_reference_expander():
    vectors = {"urgence": [1.0, 0.0]}
    rows = [_row("A", "urgence")]

    class _SpyReferenceExpander:
        def __init__(self):
            self.received: list[NodeWithScore] | None = None

        async def aexpand(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
            self.received = nodes
            return [*nodes, NodeWithScore(node=DocumentRowConverter().convert(_row("Z", "expansion")), score=None)]

    spy = _SpyReferenceExpander()
    retriever, _ = _build_retriever(vectors, rows, reference_expander=spy)
    results = await retriever.aretrieve("urgence")

    assert [n.node.node_id for n in spy.received] == ["A"]
    assert [n.node.node_id for n in results] == ["A", "Z"]


# -- reference expansion: RAMQManualRetriever wired with a real ReferenceExpander ----------
# (test_ramq_chatbot_reference_expansion.py covers ReferenceExpander's own algorithm in
# isolation; these tests only pin that RAMQManualRetriever actually wires it in, sharing the
# same fake DocumentRepository for both hybrid_search and section lookups.)


async def test_retrieve_includes_section_referenced_by_a_top_hit_even_when_it_ranks_last():
    # 21 filler rows plus a "target" whose vector is far outside the filler range: 22 rows
    # total, one more than similarity_top_k=20, and target is the single farthest — the one
    # direct retrieval cuts (see test_aretrieve_passes_similarity_top_k_through_to_hybrid_search).
    vectors = {f"code {i}": [1.0, float(i)] for i in range(21)}
    vectors["far"] = [1.0, 1000.0]
    fillers = [_row(str(i), f"code {i}") for i in range(21)]
    fillers[0] = _row("0", "code 0", metadata={"section_references": ["9.9"]})
    referenced = _row("target", "far", metadata={"section_number": "9.9"})
    rows = [*fillers, referenced]

    documents = _FakeDocumentRepository(rows, vectors)
    reference_expander = ReferenceExpander(
        section_lookup=ManualSectionLookup(documents, DocumentRowConverter()),
        codes_data=CodesData(
            _EmptyCodesTableReader(),
            __import__("app.lancedb.converter", fromlist=["CodesRowConverter"]).CodesRowConverter(),
        ),
    )
    retriever = RAMQManualRetriever(
        documents=documents,
        embed_model=_LookupEmbedding(vectors),
        query_generator=_SingleQueryGenerator(),
        fuser=ReciprocalRankFuser(),
        converter=DocumentRowConverter(),
        reference_expander=reference_expander,
    )

    results = await retriever.aretrieve("code 0")

    assert "target" in {n.node.node_id for n in results}
    assert next(n for n in results if n.node.node_id == "target").node.metadata["is_expansion"] is True


async def test_retrieve_does_not_crash_on_a_section_reference_with_no_match():
    vectors = {"urgence": [1.0, 0.0]}
    row = _row("A", "urgence", metadata={"section_references": ["9.9"]})
    retriever, _ = _build_retriever(
        vectors, [row], reference_expander=_build_reference_expander([row], vectors)
    )

    results = await retriever.aretrieve("urgence")

    assert [n.node.node_id for n in results] == ["A"]


async def test_retrieve_does_not_duplicate_a_reference_that_is_already_a_direct_hit():
    vectors = {"urgence": [1.0, 0.0], "detail": [0.9, 0.1]}
    origin = _row("A", "urgence", metadata={"section_references": ["9.9"]})
    detail = _row("B", "detail", metadata={"section_number": "9.9"})
    rows = [origin, detail]

    retriever, _ = _build_retriever(vectors, rows, reference_expander=_build_reference_expander(rows, vectors))
    results = await retriever.aretrieve("urgence")

    node_ids = [n.node.node_id for n in results]
    assert node_ids.count("B") == 1
