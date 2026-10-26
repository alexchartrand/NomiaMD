"""Reciprocal Rank Fusion (RRF), score = Σ 1/(rank + k), k=60 by default (the constant from
Cormack et al.'s original paper, also llama-index's). Lives here
(rather than under app/ramq_chatbot/, where it originated) because it's shared plumbing:
LanceDB's own hybrid_search already fuses vector+FTS *within* one query (its own RRF, see
app/lancedb/repository.py); this fuses the ranked results *across* the several queries a
multi-query planner produces for one user input — currently only
app/ramq_codes/query_planner.py's SummaryQueryPlanner for billing_codes. app/ramq_chatbot/
retriever.py used to be a second consumer (fusing across an LLM query-expander's fan-out)
but no longer fans a query out at all — see app/ramq_chatbot/retriever.py's docstring —
and dropped its dependency on this class accordingly.

Generic over the row type and its identity key: DocumentRow keys on `.id`, CodeRow/Code key
on `.number` — neither is called `id`, so the key is a constructor-injected callable rather
than a hardcoded attribute access."""

from typing import Callable, Generic, TypeVar

DEFAULT_K = 60.0

TRow = TypeVar("TRow")


class ReciprocalRankFuser(Generic[TRow]):
    """Pure RRF over already-ranked per-query hit lists. Only rank position matters — not
    the underlying `_relevance_score` values, which aren't comparable across queries — so
    each input list must already be in descending relevance order (as
    CodeRepository/DocumentRepository.hybrid_search return it)."""

    def __init__(self, key: Callable[[TRow], str] = lambda row: row.id, k: float = DEFAULT_K):
        self._key = key
        # Larger k flattens the rank curve: lower-ranked hits weigh closer to the top ones.
        self._k = k

    def fuse(self, per_query_results: list[list[TRow]], top_k: int) -> list[TRow]:
        return [row for row, _score in self.fuse_scored(per_query_results, top_k)]

    def fuse_scored(self, per_query_results: list[list[TRow]], top_k: int) -> list[tuple[TRow, float]]:
        """Same ranking as fuse(), with each row's fused score."""
        fused_scores: dict[str, float] = {}
        row_by_key: dict[str, TRow] = {}

        for results in per_query_results:
            for rank, row in enumerate(results):
                row_key = self._key(row)
                row_by_key[row_key] = row
                fused_scores[row_key] = fused_scores.get(row_key, 0.0) + 1.0 / (rank + self._k)

        ranked_keys = sorted(fused_scores, key=lambda key: fused_scores[key], reverse=True)
        return [(row_by_key[key], fused_scores[key]) for key in ranked_keys[:top_k]]
