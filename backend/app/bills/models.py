"""Bill request/response models — same style as app/claims/models.py."""

from datetime import date, datetime

from pydantic import BaseModel

from app.claims.models import ClaimOut, Money
from app.shift_claims import ShiftClaimOut


class BillCreate(BaseModel):
    start_date: date
    end_date: date
    claim_ids: list[int] = []
    # Shift claims (app/shift_claims/) — billed alongside patient claims, no NAM.
    shift_claim_ids: list[int] = []


class BillOut(BaseModel):
    id: int
    number: str
    start_date: date
    end_date: date
    generated_at: datetime
    total_amount: Money | None
    # Patient and shift claims together.
    claim_count: int


class BillDetailOut(BillOut):
    claims: list[ClaimOut]
    shift_claims: list[ShiftClaimOut]
