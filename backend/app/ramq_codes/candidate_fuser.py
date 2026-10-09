"""Second retrieval step: fuse CodeQueryRunner's per-query hit lists into one ranked candidate
list with ReciprocalRankFuser (rank-based, so the per-query relevances never have to be
comparable), then let UnresolvedAxisDetector name the eligibility axes the survivors still
depend on but the BillingContext couldn't resolve — for the prompt to ask the physician
about, never to guess.

Some queries' hits are kept whole (`kept_sources`, the visit query by default): every note
bills a visit code, the visit query is already narrowed to the visit section and the
eligible variants, and its expected code sits anywhere in its top 20 — yet with five or
more lists fused, the top-k cut falls around each list's 7th hit. So the fused top-k comes
first, then any kept hit that fell below the cut, still in RRF order.

Some queries' hits are pinned (`pinned_sources`, the care setting's visit query by default):
they come first, in their own query's order, ahead of the fused ranking. That query only
runs when the encounter's place of service is known and has its own subsection (see
query_planner.py), so its few hits are the visit codes billable there. Fused with six to
twelve other lists, one list's hits land past the cut — and the model favours the top of
the candidate list."""

from dataclasses import dataclass

from app.lancedb.fusion import ReciprocalRankFuser
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, UnresolvedAxisDetector
from app.ramq_codes.models import Code
from app.ramq_codes.query_runner import QueryResult

__all__ = [
    "DEFAULT_FUSED_TOP_K",
    "DEFAULT_KEPT_SOURCES",
    "DEFAULT_PINNED_SOURCES",
    "CandidateFuser",
    "FusedCandidate",
    "FusedCandidates",
]

DEFAULT_FUSED_TOP_K = 40
DEFAULT_KEPT_SOURCES: tuple[str, ...] = ("visit", "care_setting_visit")
DEFAULT_PINNED_SOURCES: tuple[str, ...] = ("care_setting_visit",)


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
        pinned_sources: tuple[str, ...] = DEFAULT_PINNED_SOURCES,
    ):
        """`kept_sources`: the query sources whose every hit is a candidate, past the
        fused_top_k cut; () = none. `pinned_sources`: the query sources whose hits come
        first, in their query's order (they must also be kept, or a pinned hit past the cut
        is dropped); () = none."""
        self._fuser = fuser or ReciprocalRankFuser(key=lambda code: code.number)
        self._axis_detector = axis_detector or UnresolvedAxisDetector()
        self._fused_top_k = fused_top_k
        self._kept_sources = frozenset(kept_sources)
        self._pinned_sources = frozenset(pinned_sources)

    def fuse(self, results: list[QueryResult], context: BillingContext) -> FusedCandidates:
        per_query_codes = [[hit.code for hit in result.hits] for result in results]
        kept = {hit.code.number for result in results if result.query.source in self._kept_sources for hit in result.hits}
        every_hit = sum(len(codes) for codes in per_query_codes)
        ranked = [
            FusedCandidate(code=code, rrf_score=score)
            for rank, (code, score) in enumerate(self._fuser.fuse_scored(per_query_codes, top_k=every_hit))
            if rank < self._fused_top_k or code.number in kept
        ]
        ranked = self._pin(ranked, results)
        candidates = [fused.code for fused in ranked]
        return FusedCandidates(ranked=ranked, unresolved_axes=self._axis_detector.detect(candidates, context))

    def _pin(self, ranked: list[FusedCandidate], results: list[QueryResult]) -> list[FusedCandidate]:
        """The pinned queries' hits first, in their order; the rest keeps its RRF order
        (sort is stable)."""
        pinned = [hit.code.number for result in results if result.query.source in self._pinned_sources for hit in result.hits]
        if not pinned:
            return ranked
        position = {number: i for i, number in enumerate(dict.fromkeys(pinned))}
        return sorted(ranked, key=lambda fused: position.get(fused.code.number, len(position)))
