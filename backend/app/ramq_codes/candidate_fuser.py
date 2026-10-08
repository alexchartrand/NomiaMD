"""Second retrieval step: fuse CodeQueryRunner's per-query hit lists into one ranked candidate
list with ReciprocalRankFuser (rank-based, so the per-query relevances never have to be
comparable), then let UnresolvedAxisDetector name the eligibility axes the survivors still
depend on but the BillingContext couldn't resolve — for the prompt to ask the physician
about, never to guess."""

from dataclasses import dataclass

from app.lancedb.fusion import ReciprocalRankFuser
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, UnresolvedAxisDetector
from app.ramq_codes.models import Code
from app.ramq_codes.query_runner import QueryResult

__all__ = ["DEFAULT_FUSED_TOP_K", "CandidateFuser", "FusedCandidate", "FusedCandidates"]

DEFAULT_FUSED_TOP_K = 40


@dataclass(frozen=True)
class FusedCandidate:
    code: Code
    rrf_score: float


@dataclass(frozen=True)
class FusedCandidates:
    # Descending RRF score.
    ranked: list[FusedCandidate]
    unresolved_axes: tuple[str, ...]

    @property
    def candidate_set(self) -> CandidateSet:
        return CandidateSet(candidates=[fused.code for fused in self.ranked], unresolved_axes=self.unresolved_axes)


class CandidateFuser:
    def __init__(
        self,
        fuser: ReciprocalRankFuser[Code] | None = None,
        axis_detector: UnresolvedAxisDetector | None = None,
        fused_top_k: int = DEFAULT_FUSED_TOP_K,
    ):
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._axis_detector = axis_detector or UnresolvedAxisDetector()
        self._fused_top_k = fused_top_k

    def fuse(self, results: list[QueryResult], context: BillingContext) -> FusedCandidates:
        per_query_codes = [[hit.code for hit in result.hits] for result in results]
        ranked = [
            FusedCandidate(code=code, rrf_score=score)
            for code, score in self._fuser.fuse_scored(per_query_codes, top_k=self._fused_top_k)
        ]
        candidates = [fused.code for fused in ranked]
        return FusedCandidates(ranked=ranked, unresolved_axes=self._axis_detector.detect(candidates, context))
