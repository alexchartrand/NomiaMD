"""A shift code line's fee, resolved server-side from the catalog by the shift's date — never
from the request."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.shift_claims.catalog import ShiftCode

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class ShiftLineFee:
    # None when the catalog states no fee in effect on the shift's date.
    hourly_fee: Decimal | None
    amount: Decimal | None


class ShiftFeeResolver:
    @staticmethod
    def resolve(code: ShiftCode, service_date: date, hours: int) -> ShiftLineFee:
        fee = code.fee_on(service_date)
        if fee is None:
            return ShiftLineFee(hourly_fee=None, amount=None)
        hourly = fee.per_quart / code.quart_hours
        return ShiftLineFee(
            hourly_fee=hourly.quantize(_CENT, ROUND_HALF_UP),
            amount=(hourly * hours).quantize(_CENT, ROUND_HALF_UP),
        )
