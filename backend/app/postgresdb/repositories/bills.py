"""`bills` and the `bill_claims` links grouping claims onto them."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, select, update

from app.postgresdb.models import Bill, BillClaim, Claim
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class BillInput:
    physician_id: int
    start_date: date
    end_date: date
    claim_ids: Sequence[int]
    total_amount: Decimal | None


class BillRepository(SessionRepository):
    """No relationship() — same house style as ClaimRepository. `create` and
    `delete_for_physician` each do a multi-table write (bill + link rows + the claims'
    status flip or release); they run inside the caller's single transaction, so it never
    lands only half-done."""

    async def create(self, data: BillInput) -> Bill | None:
        # Re-select the requested claims under physician + status='brouillon'. If the
        # match isn't exact, something changed since the candidate list was loaded (a
        # claim got billed or deleted concurrently) — bail out with nothing written
        # rather than silently billing a subset the physician never confirmed.
        result = await self._session.execute(
            select(Claim.id).where(
                Claim.id.in_(data.claim_ids),
                Claim.physician_id == data.physician_id,
                Claim.status == "brouillon",
            )
        )
        found_ids = set(result.scalars().all())
        if found_ids != set(data.claim_ids):
            return None

        bill = Bill(
            physician_id=data.physician_id,
            start_date=data.start_date,
            end_date=data.end_date,
            total_amount=data.total_amount,
            record_count=len(data.claim_ids),
        )
        self._session.add(bill)
        await self._session.flush()  # populate bill.id for the link rows' FK

        self._session.add_all(
            BillClaim(bill_id=bill.id, claim_id=claim_id)
            for claim_id in data.claim_ids
        )
        await self._session.execute(
            update(Claim)
            .where(Claim.id.in_(data.claim_ids))
            .values(status="soumis")
        )
        await self._session.flush()
        await self._session.refresh(bill)
        return bill

    async def list_for_physician(self, physician_id: int, *, limit: int = 100, offset: int = 0) -> list[Bill]:
        limit = min(limit, 200)
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

    async def delete_for_physician(self, bill_id: int, physician_id: int) -> bool:
        bill = await self._session.get(Bill, bill_id)
        if bill is None or bill.physician_id != physician_id:
            return False

        claim_ids = await self.claim_ids_for_bill(bill_id)
        if claim_ids:
            await self._session.execute(
                update(Claim)
                .where(Claim.id.in_(claim_ids))
                .values(status="brouillon")
            )
        await self._session.execute(delete(BillClaim).where(BillClaim.bill_id == bill_id))
        await self._session.delete(bill)
        await self._session.flush()
        return True
