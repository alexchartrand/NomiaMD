from app.lancedb.models import DocumentRow

# Reciprocal Rank Fusion, k=60 — the same constant/formula as llama_index's
# QueryFusionRetriever._reciprocal_rerank_fusion (FUSION_MODES.RECIPROCAL_RANK). LanceDB's
# own hybrid_search already fuses vector+FTS *within* one query (its own RRF, see
# app/lancedb/repository.py); this fuses the ranked results *across* the several queries
# LLMQueryGenerator produced for one user question.
_K = 60.0


class ReciprocalRankFuser:
    """Pure RRF over already-ranked per-query hit lists. Only rank position matters — not
    the underlying `_relevance_score` values, which aren't comparable across queries — so
    each input list must already be in descending relevance order (as DocumentRepository.
    hybrid_search returns it)."""

    def fuse(self, per_query_results: list[list[DocumentRow]], top_k: int) -> list[DocumentRow]:
        fused_scores: dict[str, float] = {}
        row_by_id: dict[str, DocumentRow] = {}

        for results in per_query_results:
            for rank, row in enumerate(results):
                row_by_id[row.id] = row
                fused_scores[row.id] = fused_scores.get(row.id, 0.0) + 1.0 / (rank + _K)

        ranked_ids = sorted(fused_scores, key=lambda row_id: fused_scores[row_id], reverse=True)
        return [row_by_id[row_id] for row_id in ranked_ids[:top_k]]
