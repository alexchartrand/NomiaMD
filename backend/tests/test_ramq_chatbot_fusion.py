"""Unit tests for app/ramq_chatbot/fusion.py — ReciprocalRankFuser applies the same RRF
formula (k=60) as llama_index's QueryFusionRetriever._reciprocal_rerank_fusion, but across
already-ranked per-query DocumentRow lists rather than NodeWithScore lists with raw scores —
pure algorithm, no lancedb/network involved."""

from app.lancedb.models import DocumentRow
from app.ramq_chatbot.fusion import ReciprocalRankFuser


def _row(row_id: str) -> DocumentRow:
    return DocumentRow(id=row_id, text=f"text {row_id}", title="Guide")


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
