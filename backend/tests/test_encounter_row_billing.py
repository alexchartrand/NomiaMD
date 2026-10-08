"""RowBillingSummarizer: the codes and indicative total an inbox row shows."""

from decimal import Decimal

from app.encounters.row_billing import RowBillingSummarizer
from app.extraction.models import BillingExtractionResponse, ExtractionResult
from app.postgresdb import Claim, ClaimCode, ClaimDetail
from app.ramq_codes.models import BillingCodesResult, CodeFeeOut, ExtractedCode


def _code(number: str, confidence: str, fees: list[CodeFeeOut], **retained) -> ExtractedCode:
    """`retained` defaults to confidence == "high", as for a result stored before it existed."""
    return ExtractedCode(
        code=number,
        description=number,
        confidence=confidence,
        explanation="",
        supporting_quote="",
        fees=fees,
        **retained,
    )


def _run(*codes: ExtractedCode) -> BillingExtractionResponse:
    return BillingExtractionResponse(
        billing=ExtractionResult(task="billing_codes", result=BillingCodesResult(codes=list(codes)), model="test"),
        extraction_run_id=1,
        encounter_date=None,
        encounter_date_raw=None,
    )


def _claim(*lines: tuple[str, Decimal | None]) -> ClaimDetail:
    return ClaimDetail(
        claim=Claim(),
        patient_full_name="Roch Desrosiers",
        codes=[ClaimCode(code=number, description=number, fee_amount=amount) for number, amount in lines],
    )


summarize = RowBillingSummarizer().summarize


def test_never_extracted_says_nothing():
    billing = summarize(None, None)
    assert billing.code_count is None
    assert billing.codes is None
    assert billing.indicative_total is None


def test_before_review_the_high_confidence_codes_at_their_first_fee():
    run = _run(
        _code("15804", "high", [CodeFeeOut(amount=59.8), CodeFeeOut(amount=70.0)]),
        _code("15188", "high", [CodeFeeOut(amount=27.25)]),
        _code("00103", "medium", [CodeFeeOut(amount=40.0)]),
    )

    billing = summarize(None, run)

    assert billing.code_count == 3
    assert billing.codes == ["15804", "15188"]
    assert billing.indicative_total == Decimal("87.05")


def test_a_fee_in_units_or_without_an_amount_adds_nothing():
    run = _run(
        _code("01320", "high", [CodeFeeOut(amount=5, unit="unités")]),
        _code("09001", "high", [CodeFeeOut(amount=None, amount_text="selon entente")]),
        _code("09002", "high", []),
    )

    billing = summarize(None, run)

    assert billing.codes == ["01320", "09001", "09002"]
    assert billing.indicative_total is None


def test_nothing_preselected_is_an_empty_list_not_unknown():
    billing = summarize(None, _run(_code("00103", "low", [CodeFeeOut(amount=40.0)])))
    assert billing.code_count == 1
    assert billing.codes == []
    assert billing.indicative_total is None


def test_once_billed_the_claim_wins_over_the_run():
    run = _run(_code("15804", "high", [CodeFeeOut(amount=59.8)]))
    claim = _claim(("15188", Decimal("27.25")), ("09001", None))

    billing = summarize(claim, run)

    assert billing.code_count == 2
    assert billing.codes == ["15188", "09001"]
    assert billing.indicative_total == Decimal("27.25")


def test_the_retained_codes_are_preselected_whatever_their_confidence():
    fee = [CodeFeeOut(amount=40.0)]
    row = summarize(None, _run(_code("A", "medium", fee, retained=True), _code("B", "high", fee, retained=False)))

    assert (row.code_count, row.codes, row.indicative_total) == (2, ["A"], Decimal("40.0"))
