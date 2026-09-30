"""`claims` and their `claim_codes` lines."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, func, select

from app.postgresdb.models import Claim, ClaimCode, Patient
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ClaimCodeInput:
    code: str
    description: str
    confidence: str
    explanation: str
    fee_amount: Decimal | None
    fee_when_to_use: str | None
    majoration: str | None


@dataclass
class ClaimInput:
    physician_id: int
    patient_id: int
    service_date: date
    status: str
    source_system: str | None
    summary_extraction_record_id: int | None
    billing_extraction_record_id: int | None
    codes: Sequence[ClaimCodeInput]


@dataclass
class ClaimWithCodes:
    record: Claim
    codes: list[ClaimCode]


@dataclass
class ClaimDetail:
    record: Claim
    patient_full_name: str
    codes: list[ClaimCode]


class ClaimRepository(SessionRepository):
    """No relationship() — manual second queries, matching the existing house style. Code
    rows are always written/deleted explicitly rather than leaning on claim_codes' ondelete
    CASCADE, so the delete path reads the same whichever dialect is underneath."""

    async def create(self, data: ClaimInput) -> ClaimWithCodes:
        record = Claim(
            physician_id=data.physician_id,
            patient_id=data.patient_id,
            service_date=data.service_date,
            status=data.status,
            source_system=data.source_system,
            summary_extraction_record_id=data.summary_extraction_record_id,
            billing_extraction_record_id=data.billing_extraction_record_id,
        )
        self._session.add(record)
        await self._session.flush()  # populate record.id for the code rows' FK
        code_rows = [
            ClaimCode(
                claim_id=record.id,
                code=c.code,
                description=c.description,
                confidence=c.confidence,
                explanation=c.explanation,
                fee_amount=c.fee_amount,
                fee_when_to_use=c.fee_when_to_use,
                majoration=c.majoration,
            )
            for c in data.codes
        ]
        self._session.add_all(code_rows)
        await self._session.flush()
        await self._session.refresh(record)
        for row in code_rows:
            await self._session.refresh(row)
        return ClaimWithCodes(record=record, codes=code_rows)

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        patient_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClaimDetail]:
        limit = min(limit, 200)
        # Joins Patient for the name without filtering deleted_at — a soft-deleted
        # patient's name must still render on an existing claim.
        query = (
            select(Claim, Patient.full_name)
            .join(Patient, Patient.id == Claim.patient_id)
            .where(Claim.physician_id == physician_id)
        )
        if patient_id is not None:
            query = query.where(Claim.patient_id == patient_id)
        if date_from is not None:
            query = query.where(Claim.service_date >= date_from)
        if date_to is not None:
            query = query.where(Claim.service_date <= date_to)
        if status is not None:
            query = query.where(Claim.status == status)
        query = (
            query.order_by(Claim.service_date.desc(), Claim.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rows = (await self._session.execute(query)).all()
        if not rows:
            return []
        names_by_id = {record.id: full_name for record, full_name in rows}

        code_rows = (
            await self._session.execute(
                select(ClaimCode).where(ClaimCode.claim_id.in_(names_by_id.keys()))
            )
        ).scalars().all()
        codes_by_record: dict[int, list[ClaimCode]] = {}
        for code_row in code_rows:
            codes_by_record.setdefault(code_row.claim_id, []).append(code_row)

        return [
            ClaimDetail(
                record=record,
                patient_full_name=names_by_id[record.id],
                codes=codes_by_record.get(record.id, []),
            )
            for record, _ in rows
        ]

    async def get_for_physician(self, record_id: int, physician_id: int) -> ClaimDetail | None:
        record = await self._session.get(Claim, record_id)
        if record is None or record.physician_id != physician_id:
            return None
        patient = await self._session.get(Patient, record.patient_id)
        code_rows = (
            await self._session.execute(select(ClaimCode).where(ClaimCode.claim_id == record_id))
        ).scalars().all()
        return ClaimDetail(
            record=record,
            patient_full_name=patient.full_name if patient is not None else "",
            codes=list(code_rows),
        )

    async def delete_for_physician(self, record_id: int, physician_id: int) -> bool:
        record = await self._session.get(Claim, record_id)
        if record is None or record.physician_id != physician_id:
            return False
        await self._session.execute(delete(ClaimCode).where(ClaimCode.claim_id == record_id))
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def get_by_billing_extraction_record_id(self, billing_extraction_record_id: int) -> Claim | None:
        result = await self._session.execute(
            select(Claim).where(Claim.billing_extraction_record_id == billing_extraction_record_id)
        )
        return result.scalar_one_or_none()

    async def count_for_patient_on_date(self, physician_id: int, patient_id: int, service_date: date) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Claim)
            .where(
                Claim.physician_id == physician_id,
                Claim.patient_id == patient_id,
                Claim.service_date == service_date,
            )
        )
        return result.scalar_one()
