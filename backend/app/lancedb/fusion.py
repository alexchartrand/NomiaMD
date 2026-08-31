"""Reciprocal Rank Fusion (RRF), k=60 — the same constant/formula as llama_index's
QueryFusionRetriever._reciprocal_rerank_fusion (FUSION_MODES.RECIPROCAL_RANK). Lives here
(rather than under app/ramq_chatbot/, where it originated) because both LanceDB-backed
retrievers fuse the same way now: LanceDB's own hybrid_search already fuses vector+FTS
*within* one query (its own RRF, see app/lancedb/repository.py); this fuses the ranked
results *across* the several queries a multi-query planner produced for one user input —
app/ramq_chatbot/query_generator.py's LLMQueryGenerator for the chatbot,
app/ramq_codes/query_planner.py's SummaryQueryPlanner for billing_codes.

Generic over the row type and its identity key: DocumentRow keys on `.id`, CodeRow/Code key
on `.number` — neither is called `id`, so the key is a constructor-injected callable rather
than a hardcoded attribute access."""

from typing import Callable, Generic, TypeVar

_K = 60.0

TRow = TypeVar("TRow")


class ReciprocalRankFuser(Generic[TRow]):
    """Pure RRF over already-ranked per-query hit lists. Only rank position matters — not
    the underlying `_relevance_score` values, which aren't comparable across queries — so
    each input list must already be in descending relevance order (as
    CodeRepository/DocumentRepository.hybrid_search return it)."""

    def __init__(self, key: Callable[[TRow], str] = lambda row: row.id):
        self._key = key

    def fuse(self, per_query_results: list[list[TRow]], top_k: int) -> list[TRow]:
        fused_scores: dict[str, float] = {}
        row_by_key: dict[str, TRow] = {}

        for results in per_query_results:
            for rank, row in enumerate(results):
                row_key = self._key(row)
                row_by_key[row_key] = row
                fused_scores[row_key] = fused_scores.get(row_key, 0.0) + 1.0 / (rank + _K)

        ranked_keys = sorted(fused_scores, key=lambda k: fused_scores[k], reverse=True)
        return [row_by_key[k] for k in ranked_keys[:top_k]]
