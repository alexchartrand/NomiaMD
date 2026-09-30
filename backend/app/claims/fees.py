"""Turns the fee the physician picked for a code into what a claim_codes row snapshots."""

from dataclasses import dataclass
from decimal import Decimal

from app.claims.candidates import StoredCandidate
from app.claims.errors import InvalidFeeSelectionError
from app.ramq_codes import CodeFeeOut


@dataclass(frozen=True)
class FeeSnapshot:
    amount: Decimal | None
    when_to_use: str | None
    majoration: str | None


class FeeSnapshotter:
    def snapshot(self, candidate: StoredCandidate, fee_index: int | None) -> FeeSnapshot:
        fee = self._select(candidate, fee_index)
        if fee is None:
            return FeeSnapshot(amount=None, when_to_use=None, majoration=None)
        return FeeSnapshot(
            amount=self._amount(fee),
            when_to_use=self._when_to_use(fee),
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
    def _amount(fee: CodeFeeOut) -> Decimal | None:
        # A fee in "unités" (anesthesia base units, typically an R = 2 column) is a count,
        # not a price: billing its `amount` would turn 17 units into $17. It's recorded in
        # when_to_use instead, and the claim line carries no dollar amount.
        if fee.unit != "dollars" or fee.amount is None:
            return None
        # str(amount) first: Decimal(33.15) keeps the binary float's imprecision
        # (33.14999999999999857891...); Decimal(str(33.15)) gives the exact "33.15".
        return Decimal(str(fee.amount))

    @staticmethod
    def _when_to_use(fee: CodeFeeOut) -> str | None:
        # lieux, role and a unit amount are folded into this free-text column rather than
        # given their own claim_codes columns — no Alembic in this repo, see ClaimCode's/
        # BillClaim's docstrings (app/postgresdb/models.py) for why a new column on an
        # existing table is avoided.
        parts: list[str] = []
        if fee.unit != "dollars":
            parts.append(f"{fee.amount_text or fee.amount} {fee.unit}")
        if fee.role is not None:
            parts.append(f"R = {fee.role}")
        if fee.context:
            parts.append(fee.context)
        if fee.lieux:
            parts.append(", ".join(fee.lieux))
        return " — ".join(parts) or None
