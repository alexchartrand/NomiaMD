"""Unit tests for app/ramq_chatbot/fusion.py — ReciprocalRankFuser applies the standard RRF
formula (score = Σ 1/(rank + k), k=60 by default) across already-ranked per-query DocumentRow
lists — pure algorithm, no lancedb/network involved."""

from app.lancedb.models import DocumentRow
from app.ramq_chatbot.fusion import ReciprocalRankFuser


def _row(row_id: str) -> DocumentRow:
    return DocumentRow(id=row_id, text=f"text {row_id}", title="Guide", url="https://example.test")


def test_a_row_appearing_first_in_every_query_ranks_first():
    fuser = ReciprocalRankFuser()
    a, b = _row("A"), _row("B")

    fused = fuser.fuse([[a, b], [a, b]], top_k=10)

    assert [r.id for r in fused] == ["A", "B"]


def test_a_row_appearing_in_multiple_queries_outranks_one_appearing_in_a_single_query():
    fuser = ReciprocalRankFuser()
    a, b, c = _row("A"), _row("B"), _row("C")
    # B ranks first in query 1 (best single-query rank possible), but only appears once;
    # A ranks second in both queries — RRF's cross-query reinforcement should still put A
    # ahead of a row nobody else agreed on.
    fused = fuser.fuse([[b, a], [c, a]], top_k=10)

    assert fused[0].id == "A"


def test_deduplicates_a_row_appearing_in_more_than_one_query():
    fuser = ReciprocalRankFuser()
    a = _row("A")

    fused = fuser.fuse([[a], [a], [a]], top_k=10)

    assert [r.id for r in fused] == ["A"]


def test_truncates_to_top_k():
    fuser = ReciprocalRankFuser()
    rows = [_row(str(i)) for i in range(5)]

    fused = fuser.fuse([rows], top_k=2)

    assert len(fused) == 2
    assert [r.id for r in fused] == ["0", "1"]


def test_empty_input_returns_no_rows():
    fuser = ReciprocalRankFuser()

    assert fuser.fuse([], top_k=10) == []


def test_a_query_with_no_hits_contributes_nothing():
    fuser = ReciprocalRankFuser()
    a = _row("A")

    fused = fuser.fuse([[a], []], top_k=10)

    assert [r.id for r in fused] == ["A"]


def test_fuse_scored_returns_the_rrf_score_alongside_each_row():
    a, b = _row("A"), _row("B")

    fused = ReciprocalRankFuser().fuse_scored([[a, b], [a]], top_k=10)

    assert [(row.id, round(score, 6)) for row, score in fused] == [
        ("A", round(2 / 60, 6)),
        ("B", round(1 / 61, 6)),
    ]


def test_k_sets_how_much_agreement_across_queries_outweighs_a_top_rank():
    a, b, c = _row("A"), _row("B"), _row("C")
    # B and C each top one query; A is second in both. A: 2/(1+k). B, C: 1/k.
    per_query = [[b, a], [c, a]]

    assert ReciprocalRankFuser(k=60).fuse(per_query, top_k=1)[0].id == "A"  # 2/61 > 1/60
    assert ReciprocalRankFuser(k=0.5).fuse(per_query, top_k=1)[0].id != "A"  # 2/1.5 < 1/0.5


def test_fuse_and_fuse_scored_rank_identically():
    rows = [_row(str(i)) for i in range(6)]
    per_query = [rows[:4], rows[2:], [rows[5], rows[0]]]
    fuser = ReciprocalRankFuser(k=10)

    assert [r.id for r in fuser.fuse(per_query, top_k=5)] == [r.id for r, _ in fuser.fuse_scored(per_query, top_k=5)]
