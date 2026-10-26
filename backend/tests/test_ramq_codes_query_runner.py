"""Unit tests for CodeQueryRunner (app/ramq_codes/query_runner.py), against a fake
ICodeRepository, embedding client and converter: one embedding batch for every query, one
hybrid_search per query with the caller's eligibility filter, every hit converted and kept
in order with its relevance. Real hybrid-search ranking and filtering behavior is pinned in
tests/test_lancedb_code_repository.py."""

from typing import Any

from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery
from app.ramq_codes.query_runner import CodeQueryRunner
from tests.llm_helpers import FakeEmbeddingClient

_FILTER = CodeEligibilityFilter(age=45)


class _FakeCodeRepository:
    def __init__(self, hits_by_query: dict[str, list[tuple[CodeRow, float]]]):
        self._hits_by_query = hits_by_query
        self.calls: list[dict[str, Any]] = []

    async def hybrid_search(
        self,
        text: str,
        vector: list[float],
        k: int,
        eligibility: CodeEligibilityFilter | None = None,
        sections: tuple[str, ...] | None = None,
    ) -> list[tuple[CodeRow, float]]:
        self.calls.append({"text": text, "vector": vector, "k": k, "eligibility": eligibility, "sections": sections})
        return self._hits_by_query.get(text, [])


class _FakeConverter:
    def convert(self, data: CodeRow) -> Code:
        return Code(number=data.number, description=data.description)


def _row(number: str) -> CodeRow:
    return CodeRow(number=number, description=f"description {number}", header_path="")


def _runner(
    hits_by_query: dict[str, list[tuple[CodeRow, float]]], **kwargs: Any
) -> tuple[CodeQueryRunner, _FakeCodeRepository, FakeEmbeddingClient]:
    codes = _FakeCodeRepository(hits_by_query)
    embedding_client = FakeEmbeddingClient({"visite": [1.0], "ECG": [2.0]})
    return CodeQueryRunner(codes, embedding_client, _FakeConverter(), **kwargs), codes, embedding_client


def _queries(*texts: str) -> list[PlannedQuery]:
    return [PlannedQuery(text, "visit") for text in texts]


async def test_every_query_is_embedded_in_one_batch():
    runner, _, embedding_client = _runner({})

    await runner.run(_queries("visite", "ECG", "frais"), _FILTER)

    assert embedding_client.calls == [["visite", "ECG", "frais"]]


async def test_each_query_is_searched_with_its_own_vector_and_the_eligibility_filter():
    runner, codes, _ = _runner({})

    await runner.run(_queries("visite", "ECG"), _FILTER)

    assert [(c["text"], c["vector"], c["eligibility"]) for c in codes.calls] == [
        ("visite", [1.0], _FILTER),
        ("ECG", [2.0], _FILTER),
    ]


async def test_results_keep_each_query_with_its_converted_hits_in_order():
    runner, _, _ = _runner({"visite": [(_row("A"), 0.9), (_row("B"), 0.4)], "ECG": [(_row("C"), 0.7)]})
    queries = [PlannedQuery("visite", "visit"), PlannedQuery("ECG", "procedure")]

    query_run = await runner.run(queries, _FILTER)

    assert [(r.query, [(h.code.number, h.relevance) for h in r.hits]) for r in query_run.results] == [
        (queries[0], [("A", 0.9), ("B", 0.4)]),
        (queries[1], [("C", 0.7)]),
    ]


async def test_similarity_top_k_is_passed_to_every_search():
    runner, codes, _ = _runner({}, similarity_top_k=5)

    await runner.run(_queries("visite", "ECG"), _FILTER)

    assert [c["k"] for c in codes.calls] == [5, 5]


async def test_each_search_is_limited_to_its_own_query_sections():
    runner, codes, _ = _runner({})
    queries = [PlannedQuery("visite", "visit", section_prefixes=("B —",)), PlannedQuery("ECG", "procedure")]

    await runner.run(queries, _FILTER)

    assert [c["sections"] for c in codes.calls] == [("B —",), None]
