import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import List

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.lancedb.converter import IConverter
from app.lancedb.fusion import ReciprocalRankFuser
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, EligibilityFilterFactory, UnresolvedAxisDetector
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import SummaryQueryPlanner
from app.summary.models import ConsultationSummaryResult

__all__ = ["ICodesRetriever", "RAMQCodesRetriever"]

logger = logging.getLogger(__name__)


class ICodesRetriever(ABC):
    @abstractmethod
    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        pass


class RAMQCodesRetriever(ICodesRetriever):
    """Hybrid (vector + native FTS) search over the current `codes_<rev>` LanceDB table,
    fanned out across SummaryQueryPlanner's structural per-concept queries (one for the
    visit, one per procedure/add-on the summary called out — see query_planner.py) and fused
    with ReciprocalRankFuser. Every search is prefiltered on whatever eligibility facts
    BillingContext resolves (eligibility.py), so a variant contradicting a known fact never
    takes a retrieval slot; UnresolvedAxisDetector then names the unknown axes the
    survivors still depend on, for the prompt to ask the physician about.

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
        filter_factory: EligibilityFilterFactory | None = None,
        axis_detector: UnresolvedAxisDetector | None = None,
        similarity_top_k: int = 20,
        fused_top_k: int = 40,
    ):
        self._codes = codes
        self._embed_model = embed_model
        self._converter = converter
        self._query_planner = query_planner or SummaryQueryPlanner()
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._filter_factory = filter_factory or EligibilityFilterFactory()
        self._axis_detector = axis_detector or UnresolvedAxisDetector()
        self._similarity_top_k = similarity_top_k
        self._fused_top_k = fused_top_k

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        retriever_start = time.perf_counter()

        queries = self._query_planner.plan(summary)
        eligibility = self._filter_factory.from_context(context)
        vectors = await asyncio.gather(*(self._embed_model.aget_query_embedding(q) for q in queries))

        db_start = time.perf_counter()
        per_query_hits = await asyncio.gather(
            *(
                self._codes.hybrid_search(
                    text=query, vector=vector, k=self._similarity_top_k, eligibility=eligibility
                )
                for query, vector in zip(queries, vectors)
            )
        )
        db_duration_ms = (time.perf_counter() - db_start) * 1000

        per_query_codes = [[self._converter.convert(row) for row, _score in hits] for hits in per_query_hits]

        fused = self._fuser.fuse(per_query_codes, top_k=self._fused_top_k)
        result = CandidateSet(candidates=fused, unresolved_axes=self._axis_detector.detect(fused, context))

        retriever_duration_ms = (time.perf_counter() - retriever_start) * 1000
        logger.debug(
            "RAMQCodesRetriever.aretrieve timing",
            extra={
                "retriever_duration_ms": round(retriever_duration_ms, 1),
                "db_duration_ms": round(db_duration_ms, 1),
                "query_count": len(queries),
            },
        )
        logger.debug(
            "RAMQCodesRetriever.aretrieve result",
            extra={
                "candidates": [
                    {"number": code.number, "description": code.description}
                    for code in result.candidates
                ],
                "candidate_count": len(result.candidates),
                "eligibility": asdict(eligibility),
                "unresolved_axes": list(result.unresolved_axes),
            },
        )

        return result
