"""Scores one note's stored selection (the billing_codes call) against its expected codes.

The model answers in two tiers: the codes it is sure of (`retained`, what the review ticks
and approving bills) and the other possible ones. Precision is judged on the retained codes;
recall both on them and on the two tiers together.

Each expected code is:
- retained: among the codes the model is sure of;
- possible: only among its other possible codes;
- offered_not_selected: it was among the candidates, the model left it out — a selection miss;
- not_offered: it never reached the prompt — a retrieval miss, not the model's fault.

Each returned code is correct or not; a wrong one that shares its `header_path` with an
expected code is a wrong variant (right family, wrong panel/age/registration variant).

A labeled negative (the right answer is no code) is clean when nothing came back, in either
tier. An
unlabeled note (`needs_physician_label`, no codes) is never scored for correctness. Like
retrieval, scores are recomputed from records at report time."""

from enum import StrEnum

from pydantic import BaseModel

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.records import SelectionRecord
from app.lancedb import ICodeRepository


class ExpectedStatus(StrEnum):
    RETAINED = "retained"
    POSSIBLE = "possible"
    OFFERED_NOT_SELECTED = "offered_not_selected"
    NOT_OFFERED = "not_offered"


class ExpectedSelectionOutcome(BaseModel):
    code: str
    status: ExpectedStatus


class ReturnedCodeOutcome(BaseModel):
    code: str
    # The model is sure of it (vs only possible).
    retained: bool
    # None on an unlabeled note: nothing to judge it against.
    correct: bool | None
    confidence: str
    needs_confirmation: bool
    # The expected code this one is a sibling variant of, for a wrong code.
    wrong_variant_of: str | None = None


class SelectionScore(BaseModel):
    patient_id: str
    difficulty: str
    label_status: str
    is_labeled_negative: bool
    # False for an unlabeled note.
    is_labeled: bool
    expected: list[ExpectedSelectionOutcome]
    returned: list[ReturnedCodeOutcome]
    candidate_count: int
    raw_code_count: int
    dropped_not_offered: int
    dropped_malformed: int
    error: str | None = None

    @property
    def retained(self) -> list[ReturnedCodeOutcome]:
        return [o for o in self.returned if o.retained]

    @property
    def true_positives(self) -> int:
        """Expected codes among the retained ones."""
        return sum(1 for o in self.expected if o.status == ExpectedStatus.RETAINED)

    @property
    def found_overall(self) -> int:
        """Expected codes in either tier."""
        return sum(1 for o in self.expected if o.status in (ExpectedStatus.RETAINED, ExpectedStatus.POSSIBLE))

    @property
    def exact_match(self) -> bool:
        """The model is sure of exactly the expected codes, nothing more or less."""
        return self.error is None and self.true_positives == len(self.expected) == len(self.retained)

    @property
    def clean_negative(self) -> bool:
        return self.is_labeled_negative and self.error is None and not self.returned


class SelectionScorer:
    def __init__(self, codes: ICodeRepository):
        """`codes`: the table the run read, for the codes' families (`header_path`)."""
        self._codes = codes

    async def score(self, case: BenchmarkCase, record: SelectionRecord | None) -> SelectionScore:
        error = "no selection record" if record is None else (record.error.type if record.error else None)
        offered = set(record.offered) if record else set()
        returned_codes = record.result.codes if record and record.result else []
        returned_numbers = {c.code for c in returned_codes}
        retained_numbers = {c.code for c in returned_codes if c.retained}
        is_labeled = bool(case.expected_codes) or case.is_labeled_negative

        expected = [
            ExpectedSelectionOutcome(
                code=code, status=self._expected_status(code, retained_numbers, returned_numbers, offered)
            )
            for code in sorted(case.expected_codes)
        ]

        family = await self._families(case.expected_codes | returned_numbers)
        expected_by_family = {family[c]: c for c in sorted(case.expected_codes) if family.get(c)}
        returned = []
        for code in returned_codes:
            correct = code.code in case.expected_codes if is_labeled else None
            returned.append(
                ReturnedCodeOutcome(
                    code=code.code,
                    retained=code.retained,
                    correct=correct,
                    confidence=code.confidence,
                    needs_confirmation=bool(code.needs_confirmation),
                    wrong_variant_of=expected_by_family.get(family.get(code.code, "")) if correct is False else None,
                )
            )

        return SelectionScore(
            patient_id=case.patient_id,
            difficulty=case.difficulty,
            label_status=case.label_status,
            is_labeled_negative=case.is_labeled_negative,
            is_labeled=is_labeled,
            expected=expected,
            returned=returned,
            candidate_count=len(offered),
            raw_code_count=record.raw_code_count if record else 0,
            dropped_not_offered=len(record.dropped_not_offered) if record else 0,
            dropped_malformed=record.dropped_malformed if record else 0,
            error=error,
        )

    @staticmethod
    def _expected_status(code: str, retained: set[str], returned: set[str], offered: set[str]) -> ExpectedStatus:
        if code in retained:
            return ExpectedStatus.RETAINED
        if code in returned:
            return ExpectedStatus.POSSIBLE
        if code in offered:
            return ExpectedStatus.OFFERED_NOT_SELECTED
        return ExpectedStatus.NOT_OFFERED

    async def _families(self, numbers: set[str]) -> dict[str, str]:
        if not numbers:
            return {}
        return {row.number: row.header_path for row in await self._codes.list_by_numbers(sorted(numbers)) if row.header_path}
