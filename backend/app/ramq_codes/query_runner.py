"""First retrieval step: run every planned query against the current `codes_<rev>` table.
One embedding call for all of them, then one hybrid (vector + native FTS) search per query,
each prefiltered on the eligibility facts the caller resolved — so a variant contradicting
a known fact never takes one of the k slots — and limited to the query's own sections, if
it has any. A hybrid_search hit already carries the full
row, so there's no separate hydrate-by-number step to make.

Each query's hits come back in LanceDB's own relevance order, which is all
CandidateFuser's rank-based fusion needs; the relevance itself is kept for the benchmark
(it isn't comparable across queries)."""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.lancedb.converter import IConverter
from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.lancedb.repository import ICodeRepository
from app.llm import IEmbeddingClient, call_purpose
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery

__all__ = ["DEFAULT_SIMILARITY_TOP_K", "CodeQueryRunner", "QueryHit", "QueryResult", "QueryRun"]

DEFAULT_SIMILARITY_TOP_K = 20

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryHit:
    code: Code
    # LanceDB's own vector+FTS relevance for this query; not comparable across queries.
    relevance: float


@dataclass(frozen=True)
class QueryResult:
    query: PlannedQuery
    # Descending relevance.
    hits: list[QueryHit]


@dataclass(frozen=True)
class QueryRun:
    results: list[QueryResult]
    embedding_ms: float
    db_ms: float


class CodeQueryRunner:
    def __init__(
        self,
        codes: ICodeRepository,
        embedding_client: IEmbeddingClient,
        converter: IConverter[CodeRow, Code],
        similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
    ):
        self._codes = codes
        self._embedding_client = embedding_client
        self._converter = converter
        self._similarity_top_k = similarity_top_k

    async def run(self, queries: list[PlannedQuery], eligibility: CodeEligibilityFilter) -> QueryRun:
        texts = [query.text for query in queries]

        embedding_start = time.perf_counter()
        with call_purpose("billing_codes.retrieval"):
            vectors = await self._embedding_client.embed(texts)
        embedding_ms = (time.perf_counter() - embedding_start) * 1000

        db_start = time.perf_counter()
        per_query_hits = await asyncio.gather(
            *(
                self._codes.hybrid_search(
                    text=query.text,
                    vector=vector,
                    k=self._similarity_top_k,
                    eligibility=eligibility,
                    sections=query.section_prefixes,
                )
                for query, vector in zip(queries, vectors)
            )
        )
        db_ms = (time.perf_counter() - db_start) * 1000

        logger.debug(
            "CodeQueryRunner.run timing",
            extra={
                "embedding_duration_ms": round(embedding_ms, 1),
                "db_duration_ms": round(db_ms, 1),
                "query_count": len(queries),
            },
        )

        results = [
            QueryResult(
                query=query,
                hits=[QueryHit(code=self._converter.convert(row), relevance=score) for row, score in hits],
            )
            for query, hits in zip(queries, per_query_hits)
        ]
        return QueryRun(results=results, embedding_ms=embedding_ms, db_ms=db_ms)
