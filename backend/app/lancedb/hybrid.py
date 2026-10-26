"""Hybrid (vector + full-text) search run as its two halves, each selecting its own score.

LanceDB's `query().nearest_to(...).nearest_to_text(...)` splits into a vector query and an
FTS query that share one `select(...)`. With explicit columns, lance logs a deprecation
warning on each half (the vector half for `_distance`, the FTS half for `_score`) to stderr
on every call, and neither column can be added to the shared select — each half rejects the
other's. The Python bindings don't expose `disable_scoring_autoprojection` either. So the two
halves are built here, each selecting its own score column, and fused with LanceDB's own
RRFReranker — the same rank-only fusion the hybrid query applies, so the ranking is
unchanged (score normalization doesn't move ranks)."""

import asyncio
from typing import Any

from lancedb import AsyncTable
from lancedb.query import FullTextQuery
from lancedb.rerankers import RRFReranker


class HybridSearch:
    """Runs one hybrid query over a table: the top `k` rows of the vector half and of the FTS
    half (both under the same `where`; the FTS half over `fts_columns`, every indexed column
    when None), RRF-fused, cut to `k`. Rows carry the selected `columns` plus
    `_relevance_score`, like LanceDB's hybrid query returns."""

    def __init__(self, reranker: RRFReranker | None = None):
        self._reranker = reranker or RRFReranker()

    async def search(
        self,
        table: AsyncTable,
        vector: list[float],
        text: str | FullTextQuery,
        columns: list[str],
        k: int,
        where: str | None = None,
        fts_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        vector_query = table.query().nearest_to(vector).distance_type("cosine")
        fts_query = table.query().nearest_to_text(text, columns=fts_columns)
        if where:
            vector_query = vector_query.where(where)
            fts_query = fts_query.where(where)
        vector_results, fts_results = await asyncio.gather(
            vector_query.limit(k).select([*columns, "_distance"]).with_row_id().to_arrow(),
            fts_query.limit(k).select([*columns, "_score"]).with_row_id().to_arrow(),
        )
        fused = self._reranker.rerank_hybrid(fts_query.get_query(), vector_results, fts_results)
        return fused.slice(0, k).select([*columns, "_relevance_score"]).to_pylist()
