"""Second retrieval step: fuse CodeQueryRunner's per-query hit lists into one ranked candidate
list with ReciprocalRankFuser (rank-based, so the per-query relevances never have to be
comparable), then let UnresolvedAxisDetector name the eligibility axes the survivors still
depend on but the BillingContext couldn't resolve — for the prompt to ask the physician
about, never to guess.

Some queries' hits are kept whole (`kept_sources`, the visit query by default): every note
bills a visit code, the visit query is already narrowed to the visit section and the
eligible variants, and its expected code sits anywhere in its top 20 — yet with five or
more lists fused, the top-k cut falls around each list's 7th hit. So the fused top-k comes
first, then any kept hit that fell below the cut, still in RRF order."""

from dataclasses import dataclass

from app.lancedb.fusion import ReciprocalRankFuser
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, UnresolvedAxisDetector
from app.ramq_codes.models import Code
from app.ramq_codes.query_runner import QueryResult

__all__ = ["DEFAULT_FUSED_TOP_K", "DEFAULT_KEPT_SOURCES", "CandidateFuser", "FusedCandidate", "FusedCandidates"]

DEFAULT_FUSED_TOP_K = 40
DEFAULT_KEPT_SOURCES: tuple[str, ...] = ("visit",)


@dataclass(frozen=True)
class FusedCandidate:
    code: Code
    rrf_score: float
    # Set when FamilyExpander added this code as a sibling of a retrieved one (that one's
    # number); its rrf_score is then 0 — no query ranked it.
    expanded_from: str | None = None


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
        kept_sources: tuple[str, ...] = DEFAULT_KEPT_SOURCES,
    ):
        """`kept_sources`: the query sources whose every hit is a candidate, past the
        fused_top_k cut; () = none."""
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._axis_detector = axis_detector or UnresolvedAxisDetector()
        self._fused_top_k = fused_top_k
        self._kept_sources = frozenset(kept_sources)

    def fuse(self, results: list[QueryResult], context: BillingContext) -> FusedCandidates:
        per_query_codes = [[hit.code for hit in result.hits] for result in results]
        kept = {hit.code.number for result in results if result.query.source in self._kept_sources for hit in result.hits}
        every_hit = sum(len(codes) for codes in per_query_codes)
        ranked = [
            FusedCandidate(code=code, rrf_score=score)
            for rank, (code, score) in enumerate(self._fuser.fuse_scored(per_query_codes, top_k=every_hit))
            if rank < self._fused_top_k or code.number in kept
        ]
        candidates = [fused.code for fused in ranked]
        return FusedCandidates(ranked=ranked, unresolved_axes=self._axis_detector.detect(candidates, context))
