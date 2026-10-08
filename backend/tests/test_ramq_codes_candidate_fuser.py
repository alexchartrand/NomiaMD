"""Unit tests for CandidateFuser (app/ramq_codes/candidate_fuser.py): fuses the per-query hit
lists by code number, keeps the RRF scores in candidate order, caps at fused_top_k, and hands
the fused codes plus the caller's context to the axis detector. ReciprocalRankFuser's own
scoring is pinned in tests/test_ramq_chatbot_fusion.py."""

from app.ramq_codes.candidate_fuser import CandidateFuser
from app.ramq_codes.context import BillingContext
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery
from app.ramq_codes.query_runner import QueryHit, QueryResult


class _FakeAxisDetector:
    def __init__(self):
        self.calls: list[tuple[list[Code], BillingContext]] = []

    def detect(self, candidates: list[Code], context: BillingContext) -> tuple[str, ...]:
        self.calls.append((candidates, context))
        return ("panel_size",)


def _result(text: str, *numbers: str) -> QueryResult:
    return QueryResult(
        query=PlannedQuery(text, "visit"),
        hits=[QueryHit(code=Code(number=n, description=""), relevance=1.0) for n in numbers],
    )


def test_codes_hit_by_several_queries_are_fused_into_one_candidate():
    fused = CandidateFuser(axis_detector=_FakeAxisDetector()).fuse(
        [_result("visite", "A", "B"), _result("ECG", "A")], BillingContext()
    )

    assert [c.code.number for c in fused.ranked] == ["A", "B"]


def test_rrf_scores_follow_the_candidate_order():
    fused = CandidateFuser(axis_detector=_FakeAxisDetector()).fuse(
        [_result("visite", "A", "B"), _result("ECG", "B")], BillingContext()
    )

    assert [c.code.number for c in fused.ranked] == ["B", "A"]
    assert fused.ranked[0].rrf_score > fused.ranked[1].rrf_score


def test_fused_top_k_caps_the_candidates():
    fused = CandidateFuser(axis_detector=_FakeAxisDetector(), fused_top_k=2).fuse(
        [_result("visite", *map(str, range(5)))], BillingContext()
    )

    assert len(fused.ranked) == 2


def test_the_axis_detector_sees_the_fused_codes_and_the_context():
    detector = _FakeAxisDetector()
    context = BillingContext()

    fused = CandidateFuser(axis_detector=detector).fuse([_result("visite", "A")], context)

    assert detector.calls == [([Code(number="A", description="")], context)]
    assert fused.unresolved_axes == ("panel_size",)


def test_the_candidate_set_is_the_ranked_codes_with_the_unresolved_axes():
    fused = CandidateFuser(axis_detector=_FakeAxisDetector()).fuse(
        [_result("visite", "A", "B")], BillingContext()
    )

    assert [c.number for c in fused.candidate_set.candidates] == ["A", "B"]
    assert fused.candidate_set.unresolved_axes == ("panel_size",)
