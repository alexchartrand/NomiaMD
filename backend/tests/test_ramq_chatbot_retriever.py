"""Unit tests for RAMQManualRetriever (app/ramq_chatbot/retriever.py) — a single hybrid
(vector+FTS) search over `IDocumentRepository`. No query fan-out and no RRF fusion step
(that's billing_codes' retriever now — see app/lancedb/fusion.py's docstring).

No network calls / real API keys: DocumentRepository is an in-memory fake whose
hybrid_search ranks by cosine similarity against precomputed row vectors (real FTS ranking
is LanceDB's own job — see tests/test_lancedb_document_repository.py — not something this
retriever does or needs to fake); the injected embedding client is a deterministic
exact-text-lookup fake (tests/llm_helpers.py's FakeEmbeddingClient)."""

from typing import List, Tuple

from app.ramq_chatbot.chunks import ScoredChunk
from app.ramq_chatbot.converter import DocumentRowConverter
from app.ramq_codes.converter import CodesRowConverter
from app.lancedb.models import DocumentRow
from app.lancedb.repository import ICodeRepository, IDocumentRepository
from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData
from tests.llm_helpers import FakeEmbeddingClient


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeDocumentRepository(IDocumentRepository):
    """In-memory stand-in for DocumentRepository: hybrid_search ranks rows by cosine
    similarity between the query vector and each row's own precomputed vector (looked up by
    its text, mirroring TextNode.embedding in the old vector-store-based fixtures) — actual
    per-query ranking is real DocumentRepository/LanceDB's job, not this retriever's."""

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


class _NoOpReferenceExpander:
    async def aexpand(self, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        return hits


class _EmptyCodesTableReader(ICodeRepository):
    async def get_by_number(self, number: str):
        raise NotImplementedError

    async def list_by_numbers(self, numbers: list[str]) -> list:
        return []

    async def hybrid_search(self, text: str, vector: list[float], k: int) -> list:
        raise NotImplementedError

    async def list_by_header_paths(self, header_paths: list[str], eligibility=None) -> list:
        raise NotImplementedError


def _row(row_id: str, text: str, metadata: dict | None = None) -> DocumentRow:
    metadata = metadata or {}
    return DocumentRow(
        id=row_id,
        text=text,
        title="Guide",
        url="https://example.test",
        section_number=metadata.get("section_number"),
        section_references=metadata.get("section_references"),
        code_references=metadata.get("code_references"),
    )


def _build_retriever(
    vectors: dict[str, list[float]],
    rows: list[DocumentRow],
    reference_expander=None,
    similarity_top_k: int = 20,
) -> tuple[RAMQManualRetriever, _FakeDocumentRepository]:
    documents = _FakeDocumentRepository(rows, vectors)
    retriever = RAMQManualRetriever(
        documents=documents,
        embedding_client=FakeEmbeddingClient(vectors),
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


async def test_aretrieve_ranks_best_match_first():
    vectors = {
        "urgence de nuit": [1.0, 0.0],
        "consultation de routine": [0.0, 1.0],
    }
    row_a = _row("A", "urgence de nuit")
    row_b = _row("B", "consultation de routine")

    retriever, _ = _build_retriever(vectors, [row_a, row_b])
    results = await retriever.aretrieve("urgence de nuit")

    assert results[0].chunk.id == "A"


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


async def test_aretrieve_calls_hybrid_search_once_with_the_original_query():
    vectors = {"original": [1.0, 0.0]}
    rows = [_row("A", "original")]

    retriever, documents = _build_retriever(vectors, rows)
    await retriever.aretrieve("original")

    assert [call[0] for call in documents.hybrid_search_calls] == ["original"]
    assert documents.hybrid_search_calls[0][1] == vectors["original"]


async def test_aretrieve_delegates_final_nodes_to_reference_expander():
    vectors = {"urgence": [1.0, 0.0]}
    rows = [_row("A", "urgence")]

    class _SpyReferenceExpander:
        def __init__(self):
            self.received: list[ScoredChunk] | None = None

        async def aexpand(self, hits: list[ScoredChunk]) -> list[ScoredChunk]:
            self.received = hits
            return [*hits, ScoredChunk(chunk=DocumentRowConverter().convert(_row("Z", "expansion")), score=None)]

    spy = _SpyReferenceExpander()
    retriever, _ = _build_retriever(vectors, rows, reference_expander=spy)
    results = await retriever.aretrieve("urgence")

    assert [h.chunk.id for h in spy.received] == ["A"]
    assert [h.chunk.id for h in results] == ["A", "Z"]


# -- reference expansion: RAMQManualRetriever wired with a real ReferenceExpander ----------
# (test_ramq_chatbot_reference_expansion.py covers ReferenceExpander's own algorithm in
# isolation; these tests only pin that RAMQManualRetriever actually wires it in, sharing the
# same fake DocumentRepository for both hybrid_search and section lookups.)


async def test_retrieve_includes_section_referenced_by_a_top_hit_even_when_it_ranks_last():
    # top_k + 1 filler rows plus a "target" whose vector is far outside the filler range, so
    # target is the single farthest — the one direct retrieval cuts (see
    # test_aretrieve_passes_similarity_top_k_through_to_hybrid_search). top_k is pinned rather
    # than left to the retriever's default, which would otherwise decide whether target is
    # cut at all.
    top_k = 20
    vectors = {f"code {i}": [1.0, float(i)] for i in range(top_k + 1)}
    vectors["far"] = [1.0, 1000.0]
    fillers = [_row(str(i), f"code {i}") for i in range(top_k + 1)]
    fillers[0] = _row("0", "code 0", metadata={"section_references": ["9.9"]})
    referenced = _row("target", "far", metadata={"section_number": "9.9"})
    rows = [*fillers, referenced]

    documents = _FakeDocumentRepository(rows, vectors)
    reference_expander = ReferenceExpander(
        section_lookup=ManualSectionLookup(documents, DocumentRowConverter()),
        codes_data=CodesData(
            _EmptyCodesTableReader(),
            CodesRowConverter(),
        ),
    )
    retriever = RAMQManualRetriever(
        documents=documents,
        embedding_client=FakeEmbeddingClient(vectors),
        converter=DocumentRowConverter(),
        reference_expander=reference_expander,
        similarity_top_k=top_k,
    )

    results = await retriever.aretrieve("code 0")

    assert "target" in {h.chunk.id for h in results}
    assert next(n for n in results if n.chunk.id == "target").chunk.metadata["is_expansion"] is True


async def test_retrieve_does_not_crash_on_a_section_reference_with_no_match():
    vectors = {"urgence": [1.0, 0.0]}
    row = _row("A", "urgence", metadata={"section_references": ["9.9"]})
    retriever, _ = _build_retriever(
        vectors, [row], reference_expander=_build_reference_expander([row], vectors)
    )

    results = await retriever.aretrieve("urgence")

    assert [n.chunk.id for n in results] == ["A"]


async def test_retrieve_does_not_duplicate_a_reference_that_is_already_a_direct_hit():
    vectors = {"urgence": [1.0, 0.0], "detail": [0.9, 0.1]}
    origin = _row("A", "urgence", metadata={"section_references": ["9.9"]})
    detail = _row("B", "detail", metadata={"section_number": "9.9"})
    rows = [origin, detail]

    retriever, _ = _build_retriever(vectors, rows, reference_expander=_build_reference_expander(rows, vectors))
    results = await retriever.aretrieve("urgence")

    node_ids = [n.chunk.id for n in results]
    assert node_ids.count("B") == 1
