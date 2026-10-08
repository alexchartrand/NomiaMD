"""app/benchmark/scoring.py: every expected code lands in exactly one bucket."""

from app.benchmark.scoring import CodeStatus, RetrievalScorer
from tests.benchmark_helpers import RankedCodeRepository, case, retrieval_record, row

CODES = RankedCodeRepository([
    row("A", "Visites > Suivi"),
    row("A2", "Visites > Suivi"),
    row("B", "Procédures > ECG"),
    row("REG", "Urgence", requires_registered=True),
])


async def _statuses(expected, ranked, **context):
    score = await RetrievalScorer(CODES).score(case(expected=expected, **context), retrieval_record("CLI-1", ranked))
    return {o.code: (o.status, o.rank) for o in score.outcomes}


async def test_an_offered_code_is_exact_with_its_rank():
    assert await _statuses(["B"], [("A", "Visites > Suivi"), ("B", "Procédures > ECG")]) == {"B": (CodeStatus.EXACT, 2)}


async def test_a_sibling_from_the_same_family_is_family_only():
    assert await _statuses(["A2"], [("A", "Visites > Suivi")]) == {"A2": (CodeStatus.FAMILY_ONLY, None)}


async def test_a_code_the_context_filters_out_is_ineligible_even_if_a_sibling_was_offered():
    statuses = await _statuses(["REG"], [("A", "Urgence")], is_registered=False)

    assert statuses == {"REG": (CodeStatus.INELIGIBLE, None)}


async def test_a_code_missing_from_the_table_is_not_in_table():
    assert await _statuses(["ZZZ"], []) == {"ZZZ": (CodeStatus.NOT_IN_TABLE, None)}


async def test_an_eligible_code_nobody_surfaced_is_not_retrieved():
    assert await _statuses(["B"], [("A", "Visites > Suivi")]) == {"B": (CodeStatus.NOT_RETRIEVED, None)}


async def test_the_best_query_is_the_one_that_ranked_the_code_highest():
    record = retrieval_record(
        "CLI-1", [("A", "")], queries=[("visit", ["X", "Y", "B"]), ("procedure", ["B"]), ("add_on", ["Z"])]
    )

    [outcome] = (await RetrievalScorer(CODES).score(case(expected=["B"]), record)).outcomes

    assert (outcome.best_query_source, outcome.best_query_rank) == ("procedure", 1)


async def test_a_missing_record_scores_every_code_as_missed_with_an_error():
    score = await RetrievalScorer(CODES).score(case(expected=["A"]), None)

    assert score.error == "no retrieval record"
    assert [o.status for o in score.outcomes] == [CodeStatus.NOT_RETRIEVED]
