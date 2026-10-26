"""Unit tests for FamilyExpander (app/ramq_codes/family_expander.py): each retrieved code's
eligible variants are added right after the family's best-ranked member, small families
only, with the unresolved axes re-detected over the expanded list."""

from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.ramq_codes.candidate_fuser import FusedCandidate, FusedCandidates
from app.ramq_codes.context import BillingContext
from app.ramq_codes.converter import CodesRowConverter
from app.ramq_codes.family_expander import FamilyExpander
from tests.conftest import StubCodeRepository

_LEVEL_A = "B > CHSGS > Niveau A"
_SUPPLEMENTS = "B > CHSLD"
_FILTER = CodeEligibilityFilter(age=66)


def _row(number: str, header_path: str, **bounds) -> CodeRow:
    return CodeRow(number=number, description=f"description {number}", header_path=header_path, **bounds)


_ROWS = [
    _row("15638", _LEVEL_A),
    _row("15639", _LEVEL_A),
    _row("15643", _LEVEL_A),
    _row("15644", _LEVEL_A, min_age=80),  # ineligible at 66
    _row("15623", _SUPPLEMENTS),
    _row("15624", _SUPPLEMENTS),
    _row("00431", "C > Injection"),
    _row("X", ""),
    _row("Y", ""),
]
_CONVERTER = CodesRowConverter()


def _fused(*numbers: str, axes: tuple[str, ...] = ()) -> FusedCandidates:
    by_number = {r.number: r for r in _ROWS}
    return FusedCandidates(
        ranked=[
            FusedCandidate(code=_CONVERTER.convert(by_number[n]), rrf_score=1.0 / (i + 1)) for i, n in enumerate(numbers)
        ],
        unresolved_axes=axes,
    )


async def _expand(fused: FusedCandidates, max_family_size: int = 12, rows=_ROWS) -> FusedCandidates:
    expander = FamilyExpander(StubCodeRepository(rows), _CONVERTER, max_family_size=max_family_size)
    return await expander.expand(fused, _FILTER, BillingContext())


async def test_eligible_siblings_follow_the_family_member_that_was_retrieved():
    expanded = await _expand(_fused("15639", "00431"))

    assert [(c.code.number, c.expanded_from) for c in expanded.ranked] == [
        ("15639", None),
        ("15638", "15639"),
        ("15643", "15639"),
        ("00431", None),
    ]


async def test_added_siblings_have_no_rrf_score_and_retrieved_ones_keep_theirs():
    expanded = await _expand(_fused("15639"))

    assert [c.rrf_score for c in expanded.ranked] == [1.0, 0.0, 0.0]


async def test_a_sibling_retrieved_further_down_keeps_its_own_place_and_is_not_duplicated():
    expanded = await _expand(_fused("15643", "00431", "15638"))

    assert [c.code.number for c in expanded.ranked] == ["15643", "15639", "00431", "15638"]


async def test_families_larger_than_the_cap_are_left_alone():
    expanded = await _expand(_fused("15639", "15623"), max_family_size=2)

    assert [c.code.number for c in expanded.ranked] == ["15639", "15623", "15624"]


async def test_a_zero_cap_turns_expansion_off():
    fused = _fused("15639")

    assert await _expand(fused, max_family_size=0) is fused


async def test_codes_with_no_header_path_are_never_grouped_together():
    expanded = await _expand(_fused("X"))

    assert [c.code.number for c in expanded.ranked] == ["X"]


async def test_unresolved_axes_are_detected_over_the_expanded_list():
    rows = [_row("A", "B > fam"), _row("B", "B > fam", min_panel_size=500)]

    expanded = await _expand(FusedCandidates(ranked=[FusedCandidate(code=_CONVERTER.convert(rows[0]), rrf_score=1.0)], unresolved_axes=()), rows=rows)

    assert expanded.unresolved_axes == ("panel_size",)
