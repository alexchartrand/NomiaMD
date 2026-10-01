"""Claim ORM rows → API shapes. Shared by ClaimService and app/bills/service.py, which
renders a bill's claims the same way."""

from decimal import Decimal
from typing import Iterable

from app.claims.models import ClaimCodeOut, ClaimOut
from app.claims.status import ClaimLifecycle
from app.postgresdb import Claim, ClaimCode, ClaimDetail


class ClaimMapper:
    @staticmethod
    def codes_out(codes: Iterable[ClaimCode]) -> list[ClaimCodeOut]:
        return [ClaimCodeOut.model_validate(c) for c in codes]

    @staticmethod
    def total_amount(codes: list[ClaimCodeOut]) -> Decimal | None:
        amounts = [c.fee_amount for c in codes if c.fee_amount is not None]
        return sum(amounts) if amounts else None

    @classmethod
    def to_out(cls, claim: Claim, patient_full_name: str, codes: Iterable[ClaimCode]) -> ClaimOut:
        codes_out = cls.codes_out(codes)
        return ClaimOut(
            id=claim.id,
            patient_id=claim.patient_id,
            patient_full_name=patient_full_name,
            service_date=claim.service_date,
            status=ClaimLifecycle.status_of(claim),
            bill_id=claim.bill_id,
            source_system=claim.source_system,
            codes=codes_out,
            total_amount=cls.total_amount(codes_out),
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )

    @classmethod
    def from_detail(cls, detail: ClaimDetail) -> ClaimOut:
        return cls.to_out(detail.claim, detail.patient_full_name, detail.codes)
