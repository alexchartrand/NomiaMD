"""`bills` and the `bill_claims` links grouping claims onto them."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Bill, BillClaim
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class BillInput:
    physician_id: int
    start_date: date
    end_date: date
    claim_ids: Sequence[int]
    total_amount: Decimal | None


class ClaimAlreadyBilledError(Exception):
    """A requested claim is already linked to another bill — bill_claims' unique claim_id
    index is the backstop for two bills racing over the same claim. The session can only be
    rolled back afterwards, which its owner does as this propagates (see session.py)."""


class BillRepository(SessionRepository):
    """Stores bills and the claims they group — nothing more. Which claims may be billed,
    and the status change that goes with it, belong to BillService and
    app/claims/status.py's ClaimLifecycle; both run in the same transaction as these writes.
    No relationship() — same house style as ClaimRepository."""

    async def create(self, data: BillInput) -> Bill:
        bill = Bill(
            physician_id=data.physician_id,
            start_date=data.start_date,
            end_date=data.end_date,
            total_amount=data.total_amount,
            claim_count=len(data.claim_ids),
        )
        self._session.add(bill)
        await self._session.flush()  # populate bill.id for the link rows' FK

        self._session.add_all(BillClaim(bill_id=bill.id, claim_id=claim_id) for claim_id in data.claim_ids)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ClaimAlreadyBilledError() from exc
        await self._session.refresh(bill)
        return bill

    async def list_for_physician(self, physician_id: int, *, limit: int = 100, offset: int = 0) -> list[Bill]:
        result = await self._session.execute(
            select(Bill)
            .where(Bill.physician_id == physician_id)
            .order_by(Bill.generated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_for_physician(self, bill_id: int, physician_id: int) -> Bill | None:
        bill = await self._session.get(Bill, bill_id)
        if bill is None or bill.physician_id != physician_id:
            return None
        return bill

    async def claim_ids_for_bill(self, bill_id: int) -> list[int]:
        result = await self._session.execute(
            select(BillClaim.claim_id).where(BillClaim.bill_id == bill_id)
        )
        return list(result.scalars().all())

    async def delete(self, bill: Bill) -> None:
        # Link rows first, explicitly — same "don't lean on ondelete CASCADE" convention as
        # ClaimRepository's code rows.
        await self._session.execute(delete(BillClaim).where(BillClaim.bill_id == bill.id))
        await self._session.delete(bill)
        await self._session.flush()
