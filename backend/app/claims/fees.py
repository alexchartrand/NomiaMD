"""Turns the fee the physician picked for a code into what a claim_codes row snapshots."""

from dataclasses import dataclass
from decimal import Decimal

from app.claims.candidates import StoredCandidate
from app.claims.errors import InvalidFeeSelectionError
from app.ramq_codes import CodeFeeOut


@dataclass(frozen=True)
class FeeSnapshot:
    amount: Decimal | None = None
    unit: str | None = None
    units: Decimal | None = None
    role: int | None = None
    context: str | None = None
    lieux: list[str] | None = None
    majoration: str | None = None


class FeeSnapshotter:
    def snapshot(self, candidate: StoredCandidate, fee_index: int | None) -> FeeSnapshot:
        fee = self._select(candidate, fee_index)
        if fee is None:
            return FeeSnapshot()
        is_dollars = fee.unit == "dollars"
        # A fee in "unités" (anesthesia base units, typically an R = 2 column) is a count,
        # not a price: billing its `amount` would turn 17 units into $17. The count goes in
        # `units` instead, and the claim line carries no dollar amount.
        amount = self._decimal(fee.amount)
        return FeeSnapshot(
            amount=amount if is_dollars else None,
            unit=fee.unit,
            units=None if is_dollars else amount,
            role=fee.role,
            context=fee.context,
            lieux=list(fee.lieux) or None,
            majoration=fee.majoration,
        )

    @staticmethod
    def _select(candidate: StoredCandidate, fee_index: int | None) -> CodeFeeOut | None:
        if not candidate.fees:
            return None
        index = fee_index if fee_index is not None else 0
        if index < 0 or index >= len(candidate.fees):
            raise InvalidFeeSelectionError(candidate.code, index, len(candidate.fees))
        return candidate.fees[index]

    @staticmethod
    def _decimal(value: float | None) -> Decimal | None:
        # str(value) first: Decimal(33.15) keeps the binary float's imprecision
        # (33.14999999999999857891...); Decimal(str(33.15)) gives the exact "33.15".
        return Decimal(str(value)) if value is not None else None
