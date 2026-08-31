"""Unit tests for RAMQCodesRetriever (app/ramq_codes/retriever.py).

Exercised against fakes for every collaborator (ICodeRepository, embedding model,
converter, SummaryQueryPlanner, ReciprocalRankFuser, CodeFamilySelector) — this file only
pins RAMQCodesRetriever's own responsibility: plan queries from the summary, embed and
hybrid_search each one, convert every hit, fuse across queries, then hand the fused list and
the caller's BillingContext to the family selector and return its result untouched.
SummaryQueryPlanner and CodeFamilySelector each have their own dedicated unit tests
(test_ramq_codes_query_planner.py, test_ramq_codes_family.py); real hybrid-search ranking
behavior is pinned in tests/test_lancedb_code_repository.py."""

from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.lancedb.fusion import ReciprocalRankFuser
from app.lancedb.models import CodeRow
from app.ramq_codes.context import BillingContext
from app.ramq_codes.family import FamilyCollapseResult
from app.ramq_codes.models import Code
from app.ramq_codes.retriever import RAMQCodesRetriever
from tests.test_consultation_summary import MOCK_RESULT
from app.summary import ConsultationSummaryResult

SUMMARY = ConsultationSummaryResult.model_validate(MOCK_RESULT)


class _FakeCodeRepository:
    def __init__(self, hits_by_query: dict[str, list[tuple[CodeRow, float]]]):
        self._hits_by_query = hits_by_query
        self.calls: list[dict[str, Any]] = []

    async def hybrid_search(self, text: str, vector: list[float], k: int) -> list[tuple[CodeRow, float]]:
        self.calls.append({"text": text, "vector": vector, "k": k})
        return self._hits_by_query.get(text, [])


class _LookupEmbedding(BaseEmbedding):
    vectors: dict[str, list[float]]

    def __init__(self, vectors: dict[str, list[float]], **kwargs: Any):
        super().__init__(vectors=vectors, **kwargs)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self.vectors.get(query, [0.0])

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self.vectors.get(query, [0.0])

    def _get_text_embedding(self, text: str) -> list[float]:
        return self.vectors.get(text, [0.0])

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self.vectors.get(text, [0.0])


class _FakeConverter:
    def convert(self, data: CodeRow) -> Code:
        return Code(number=data.number, libelle=data.libelle, description=data.description)


class _FakeQueryPlanner:
    def __init__(self, queries: list[str]):
        self._queries = queries
        self.plan_calls: list[ConsultationSummaryResult] = []

    def plan(self, summary: ConsultationSummaryResult) -> list[str]:
        self.plan_calls.append(summary)
        return self._queries


class _FakeFamilySelector:
    def __init__(self):
        self.calls: list[tuple[list[Code], BillingContext]] = []

    def select(self, candidates: list[Code], context: BillingContext) -> FamilyCollapseResult:
        self.calls.append((candidates, context))
        return FamilyCollapseResult(candidates=candidates, unresolved_axes=("panel_size",))


def _row(number: str) -> CodeRow:
    return CodeRow(number=number, libelle=f"libelle {number}", description=f"description {number}", header_path="")


def _retriever(
    hits_by_query: dict[str, list[tuple[CodeRow, float]]],
    *,
    planner_queries: list[str],
    family_selector: _FakeFamilySelector | None = None,
    **kwargs: Any,
) -> tuple[RAMQCodesRetriever, _FakeCodeRepository, _FakeFamilySelector]:
    codes = _FakeCodeRepository(hits_by_query)
    embed_model = _LookupEmbedding({})
    selector = family_selector or _FakeFamilySelector()
    retriever = RAMQCodesRetriever(
        codes,
        embed_model,
        _FakeConverter(),
        query_planner=_FakeQueryPlanner(planner_queries),
        family_selector=selector,
        **kwargs,
    )
    return retriever, codes, selector


async def test_aretrieve_searches_once_per_planned_query():
    retriever, codes, _ = _retriever(
        {"visite": [(_row("A"), 0.9)], "procédure": [(_row("B"), 0.5)]},
        planner_queries=["visite", "procédure"],
    )

    await retriever.aretrieve(SUMMARY, BillingContext())

    assert [call["text"] for call in codes.calls] == ["visite", "procédure"]


async def test_aretrieve_fuses_across_queries_and_dedupes():
    retriever, _, selector = _retriever(
        {"visite": [(_row("A"), 0.9), (_row("B"), 0.5)], "procédure": [(_row("A"), 0.9)]},
        planner_queries=["visite", "procédure"],
    )

    await retriever.aretrieve(SUMMARY, BillingContext())

    (fused_candidates, _context) = selector.calls[0]
    assert sorted(c.number for c in fused_candidates) == ["A", "B"]


async def test_aretrieve_passes_the_context_through_to_the_family_selector():
    retriever, _, selector = _retriever({"visite": [(_row("A"), 0.9)]}, planner_queries=["visite"])
    context = BillingContext()

    await retriever.aretrieve(SUMMARY, context)

    assert selector.calls[0][1] is context


async def test_aretrieve_returns_the_family_selectors_result_untouched():
    retriever, _, selector = _retriever({"visite": [(_row("A"), 0.9)]}, planner_queries=["visite"])

    result = await retriever.aretrieve(SUMMARY, BillingContext())

    assert result.unresolved_axes == ("panel_size",)


async def test_aretrieve_respects_a_custom_similarity_top_k():
    retriever, codes, _ = _retriever({"visite": []}, planner_queries=["visite"], similarity_top_k=5)

    await retriever.aretrieve(SUMMARY, BillingContext())

    assert codes.calls[0]["k"] == 5


async def test_aretrieve_respects_a_custom_fused_top_k():
    hits = [(_row(str(i)), 1.0) for i in range(5)]
    retriever, _, selector = _retriever({"visite": hits}, planner_queries=["visite"], fused_top_k=2)

    await retriever.aretrieve(SUMMARY, BillingContext())

    (fused_candidates, _context) = selector.calls[0]
    assert len(fused_candidates) == 2


def test_default_fuser_keys_on_code_number():
    fuser: ReciprocalRankFuser[Code] = ReciprocalRankFuser(key=lambda code: code.number)
    a = Code(number="A", libelle="", description="")

    fused = fuser.fuse([[a], [a]], top_k=10)

    assert [c.number for c in fused] == ["A"]
