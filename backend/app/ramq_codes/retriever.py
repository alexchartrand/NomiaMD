import asyncio
from abc import ABC, abstractmethod
from typing import List

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.lancedb.converter import IConverter
from app.lancedb.fusion import ReciprocalRankFuser
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.context import BillingContext
from app.ramq_codes.family import CodeFamilySelector, FamilyCollapseResult
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import SummaryQueryPlanner
from app.summary.models import ConsultationSummaryResult

__all__ = ["ICodesRetriever", "RAMQCodesRetriever"]


class ICodesRetriever(ABC):
    @abstractmethod
    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> FamilyCollapseResult:
        pass


class RAMQCodesRetriever(ICodesRetriever):
    """Hybrid (vector + native FTS) search over the flat `codes` LanceDB table, fanned out
    across SummaryQueryPlanner's structural per-concept queries (one for the visit, one per
    procedure/add-on the summary called out — see query_planner.py) and fused with
    ReciprocalRankFuser, then narrowed by CodeFamilySelector against whatever
    BillingContext resolves (family.py) — the axis-disambiguation step that used to be left
    entirely to the LLM's guess.

    Replaces the old single-query VectorStoreIndex/BM25Retriever/QueryFusionRetriever stack
    (that in-memory BM25 corpus scan and English stemmer only existed because the previous
    `code-embeddings` table had no native FTS index; the flat `codes` table does — see
    ramq-ingestion's docs/plans/flat-lancedb-codes-table.md). A hybrid_search hit already
    carries the full row, so there's no separate hydrate-by-number step to make."""

    def __init__(
        self,
        codes: ICodeRepository,
        embed_model: BaseEmbedding,
        converter: IConverter,
        query_planner: SummaryQueryPlanner | None = None,
        fuser: ReciprocalRankFuser[Code] | None = None,
        family_selector: CodeFamilySelector | None = None,
        similarity_top_k: int = 20,
        fused_top_k: int = 40,
    ):
        self._codes = codes
        self._embed_model = embed_model
        self._converter = converter
        self._query_planner = query_planner or SummaryQueryPlanner()
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._family_selector = family_selector or CodeFamilySelector()
        self._similarity_top_k = similarity_top_k
        self._fused_top_k = fused_top_k

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> FamilyCollapseResult:
        queries = self._query_planner.plan(summary)
        vectors = await asyncio.gather(*(self._embed_model.aget_query_embedding(q) for q in queries))

        per_query_hits = await asyncio.gather(
            *(
                self._codes.hybrid_search(text=query, vector=vector, k=self._similarity_top_k)
                for query, vector in zip(queries, vectors)
            )
        )
        per_query_codes = [[self._converter.convert(row) for row, _score in hits] for hits in per_query_hits]

        fused = self._fuser.fuse(per_query_codes, top_k=self._fused_top_k)
        return self._family_selector.select(fused, context)
