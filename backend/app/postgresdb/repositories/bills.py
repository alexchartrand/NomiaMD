"""`bills` — the invoice headers. Which claims a bill groups is Claim.bill_id, written by
ClaimRepository.attach_to_bill."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.postgresdb.models import Bill
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class BillInput:
    physician_id: int
    start_date: date
    end_date: date
    claim_count: int
    total_amount: Decimal | None


class BillRepository(SessionRepository):
    """Stores bills — nothing more. Which claims may be billed, and attaching them, belong
    to BillService and ClaimRepository, both in the same transaction as these writes.
    Voided bills are invisible to every read here."""

    async def create(self, data: BillInput) -> Bill:
        bill = Bill(
            physician_id=data.physician_id,
            start_date=data.start_date,
            end_date=data.end_date,
            total_amount=data.total_amount,
            claim_count=data.claim_count,
        )
        self._session.add(bill)
        await self._session.flush()
        return bill

    async def list_for_physician(self, physician_id: int, *, limit: int = 100, offset: int = 0) -> list[Bill]:
        result = await self._session.execute(
            select(Bill)
            .where(Bill.physician_id == physician_id, Bill.voided_at.is_(None))
            # id breaks ties: generated_at comes from the DB clock, which SQLite only
            # keeps to the second.
            .order_by(Bill.generated_at.desc(), Bill.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_generated_between(self, physician_id: int, start: datetime, end: datetime) -> list[Bill]:
        """Bills generated from `start` (included) to `end` (excluded) — instants, so the
        caller decides whose calendar a month is (the clinic's, app/clock.py)."""
        result = await self._session.execute(
            select(Bill)
            .where(
                Bill.physician_id == physician_id,
                Bill.voided_at.is_(None),
                Bill.generated_at >= start,
                Bill.generated_at < end,
            )
            .order_by(Bill.generated_at.desc(), Bill.id.desc())
        )
        return list(result.scalars().all())

    async def get_for_physician(self, bill_id: int, physician_id: int) -> Bill | None:
        bill = await self._session.get(Bill, bill_id)
        if bill is None or bill.physician_id != physician_id or bill.voided_at is not None:
            return None
        return bill

    async def void(self, bill: Bill) -> None:
        bill.voided_at = datetime.now(timezone.utc)
        await self._session.flush()
