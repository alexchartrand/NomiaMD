import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict

from app.lancedb.converter import IConverter
from app.lancedb.models import CodeRow
from app.lancedb.fusion import ReciprocalRankFuser
from app.lancedb.repository import ICodeRepository
from app.llm import IEmbeddingClient, call_purpose
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, EligibilityFilterFactory, UnresolvedAxisDetector
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery, SummaryQueryPlanner
from app.ramq_codes.retrieval_trace import FusedCandidate, QueryHit, QueryTrace, RetrievalTrace
from app.summary.models import ConsultationSummaryResult

__all__ = ["ICodesRetriever", "RAMQCodesRetriever"]

DEFAULT_SIMILARITY_TOP_K = 20
DEFAULT_FUSED_TOP_K = 40

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
        embedding_client: IEmbeddingClient,
        converter: IConverter[CodeRow, Code],
        query_planner: SummaryQueryPlanner | None = None,
        fuser: ReciprocalRankFuser[Code] | None = None,
        filter_factory: EligibilityFilterFactory | None = None,
        axis_detector: UnresolvedAxisDetector | None = None,
        similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
        fused_top_k: int = DEFAULT_FUSED_TOP_K,
    ):
        self._codes = codes
        self._embedding_client = embedding_client
        self._converter = converter
        self._query_planner = query_planner or SummaryQueryPlanner()
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._filter_factory = filter_factory or EligibilityFilterFactory()
        self._axis_detector = axis_detector or UnresolvedAxisDetector()
        self._similarity_top_k = similarity_top_k
        self._fused_top_k = fused_top_k

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        return (await self.aretrieve_traced(summary, context)).candidate_set

    async def aretrieve_traced(self, summary: ConsultationSummaryResult, context: BillingContext) -> RetrievalTrace:
        return await self.aretrieve_queries(self._query_planner.plan_labeled(summary), context)

    async def aretrieve_queries(self, queries: list[PlannedQuery], context: BillingContext) -> RetrievalTrace:
        """The retrieval itself, over whatever queries the caller planned — the summary's
        (aretrieve), the raw transcript's, or both (the benchmark's control runs)."""
        retriever_start = time.perf_counter()
        texts = [query.text for query in queries]
        eligibility = self._filter_factory.from_context(context)

        # One embedding call for every planned query.
        with call_purpose("billing_codes.retrieval"):
            vectors = await self._embedding_client.embed(texts)
        embedding_ms = (time.perf_counter() - retriever_start) * 1000

        db_start = time.perf_counter()
        per_query_hits = await asyncio.gather(
            *(
                self._codes.hybrid_search(
                    text=text, vector=vector, k=self._similarity_top_k, eligibility=eligibility
                )
                for text, vector in zip(texts, vectors)
            )
        )
        db_ms = (time.perf_counter() - db_start) * 1000

        per_query_codes = [[self._converter.convert(row) for row, _score in hits] for hits in per_query_hits]
        fused = self._fuser.fuse_scored(per_query_codes, top_k=self._fused_top_k)
        candidates = [code for code, _score in fused]
        trace = RetrievalTrace(
            candidate_set=CandidateSet(candidates=candidates, unresolved_axes=self._axis_detector.detect(candidates, context)),
            queries=[
                QueryTrace(query=query, hits=[QueryHit(number=row.number, relevance=score) for row, score in hits])
                for query, hits in zip(queries, per_query_hits)
            ],
            fused=[FusedCandidate(code=code, rrf_score=score) for code, score in fused],
            eligibility=eligibility,
            embedding_ms=embedding_ms,
            db_ms=db_ms,
        )

        logger.debug(
            "RAMQCodesRetriever.aretrieve timing",
            extra={
                "retriever_duration_ms": round((time.perf_counter() - retriever_start) * 1000, 1),
                "db_duration_ms": round(db_ms, 1),
                "query_count": len(queries),
            },
        )
        logger.debug(
            "RAMQCodesRetriever.aretrieve result",
            extra={
                "candidates": [{"number": code.number, "description": code.description} for code in candidates],
                "candidate_count": len(candidates),
                "eligibility": asdict(eligibility),
                "unresolved_axes": list(trace.candidate_set.unresolved_axes),
            },
        )

        return trace
