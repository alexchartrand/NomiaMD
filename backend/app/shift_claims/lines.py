"""The physician's confirmed codes -> the shift_claim_codes rows a shift claim is saved with:
each code checked against the catalog and the shift, its description, secteur de dispensation
and fee snapshotted from the catalog on the shift's date — never from the request."""

from app.care_setting import CareSetting
from app.claims.origin import CodeOrigin
from app.postgresdb import ShiftClaimCodeInput
from app.shift_claims.catalog import GardeOption, ShiftCodeCatalog
from app.shift_claims.errors import (
    EmptyShiftClaimError,
    HoursExceedShiftError,
    IncompatibleShiftCodesError,
    UnknownShiftCodeError,
    WholeQuartsOnlyError,
)
from app.shift_claims.fees import ShiftFeeResolver
from app.shift_claims.models import ShiftClaimLineIn
from app.shift_claims.rules import SuggestedShiftLine
from app.shifts import ShiftHours


class ShiftClaimLineBuilder:
    def __init__(self, catalog: ShiftCodeCatalog, fees: ShiftFeeResolver | None = None) -> None:
        self._catalog = catalog
        self._fees = fees or ShiftFeeResolver()

    def build(
        self,
        lines: list[ShiftClaimLineIn],
        *,
        care_setting: CareSetting | None,
        hours: ShiftHours,
        suggested: list[SuggestedShiftLine],
        garde_option: GardeOption = GardeOption.ACTE,
    ) -> list[ShiftClaimCodeInput]:
        """First line per code wins. A code may run up to the shift's whole hours: the rules'
        count is a suggestion, and an établissement's own holiday calendar can differ from
        the default one they read."""
        by_code: dict[str, ShiftClaimLineIn] = {}
        for line in lines:
            by_code.setdefault(line.code, line)
        if not by_code:
            raise EmptyShiftClaimError()
        for number in by_code:
            clash = sorted(self._catalog.excluded_with(number) & by_code.keys())
            if clash:
                raise IncompatibleShiftCodesError(number, clash[0])
        suggested_codes = {line.code.number for line in suggested}
        shift_hours = int(hours.duration.total_seconds() // 3600)
        rows = []
        for line in by_code.values():
            code = self._catalog.get(line.code)
            if code is None or care_setting is None or not code.applies_to(care_setting, garde_option):
                raise UnknownShiftCodeError(line.code)
            if line.hours > shift_hours:
                raise HoursExceedShiftError(line.code, line.hours, shift_hours)
            if not code.divisible_in_hours and line.hours % code.quart_hours:
                raise WholeQuartsOnlyError(line.code, code.quart_hours)
            fee = self._fees.resolve(code, hours.service_date, line.hours)
            rows.append(
                ShiftClaimCodeInput(
                    code=code.number,
                    description=code.description,
                    origin=(CodeOrigin.SUGGESTED if code.number in suggested_codes else CodeOrigin.MANUAL).value,
                    hours=line.hours,
                    hourly_fee=fee.hourly_fee,
                    fee_amount=fee.amount,
                    secteur_dispensation=code.secteur_dispensation,
                    secteur_dispensation_label=self._catalog.secteur_label(code.secteur_dispensation) or "",
                    source=code.citation,
                )
            )
        return rows
