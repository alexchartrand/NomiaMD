"""Shift claim rows and catalog codes -> API shapes. Shared by ShiftClaimService and
app/bills/service.py, which renders a bill's shift claims the same way."""

from datetime import date
from decimal import Decimal
from typing import Iterable

from app.claims.status import ClaimLifecycle
from app.postgresdb import ShiftClaimCode, ShiftClaimDetail
from app.shift_claims.catalog import ShiftCode, ShiftCodeCatalog
from app.shift_claims.fees import ShiftFeeResolver
from app.shift_claims.models import ShiftClaimCodeOut, ShiftClaimOut, ShiftCodeOut, SuggestedShiftCodeOut
from app.shift_claims.rules import SuggestedShiftLine
from app.shifts import ShiftHours


class ShiftClaimMapper:
    @staticmethod
    def codes_out(codes: Iterable[ShiftClaimCode]) -> list[ShiftClaimCodeOut]:
        return [ShiftClaimCodeOut.model_validate(code) for code in codes]

    @staticmethod
    def total_amount(codes: list[ShiftClaimCodeOut]) -> Decimal | None:
        amounts = [code.fee_amount for code in codes if code.fee_amount is not None]
        return sum(amounts) if amounts else None

    @classmethod
    def from_detail(cls, detail: ShiftClaimDetail) -> ShiftClaimOut:
        claim = detail.claim
        codes = cls.codes_out(detail.codes)
        return ShiftClaimOut(
            id=claim.id,
            shift_id=claim.shift_id,
            service_date=claim.service_date,
            start_time=claim.start_time,
            end_time=claim.end_time,
            ends_next_day=ShiftHours(claim.service_date, claim.start_time, claim.end_time).ends_next_day,
            care_setting=claim.care_setting,
            period=claim.period,
            work_site_name=claim.work_site_name,
            status=ClaimLifecycle.status_of(claim),
            bill_id=claim.bill_id,
            codes=codes,
            total_amount=cls.total_amount(codes),
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )


class ShiftCodeMapper:
    def __init__(self, catalog: ShiftCodeCatalog, fees: ShiftFeeResolver | None = None) -> None:
        self._catalog = catalog
        self._fees = fees or ShiftFeeResolver()

    def _secteur_label(self, code: ShiftCode) -> str:
        # The catalog checks every code's secteur on load: never missing.
        return self._catalog.secteur_label(code.secteur_dispensation) or ""

    def suggested(self, line: SuggestedShiftLine, service_date: date) -> SuggestedShiftCodeOut:
        fee = self._fees.resolve(line.code, service_date, line.hours)
        return SuggestedShiftCodeOut(
            code=line.code.number,
            description=line.code.description,
            hours=line.hours,
            hourly_fee=fee.hourly_fee,
            fee_amount=fee.amount,
            secteur_dispensation=line.code.secteur_dispensation,
            secteur_dispensation_label=self._secteur_label(line.code),
            source=line.code.citation,
        )

    def available(self, code: ShiftCode, service_date: date) -> ShiftCodeOut:
        return ShiftCodeOut(
            code=code.number,
            description=code.description,
            quart_hours=code.quart_hours,
            divisible_in_hours=code.divisible_in_hours,
            hourly_fee=self._fees.resolve(code, service_date, 1).hourly_fee,
            secteur_dispensation=code.secteur_dispensation,
            secteur_dispensation_label=self._secteur_label(code),
            source=code.citation,
        )
