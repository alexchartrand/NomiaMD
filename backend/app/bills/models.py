"""Bill request/response models — same style as app/claims/models.py."""

from datetime import date, datetime

from pydantic import BaseModel

from app.claims.models import ClaimOut, Money


class BillCreate(BaseModel):
    start_date: date
    end_date: date
    claim_ids: list[int]


class BillOut(BaseModel):
    id: int
    number: str
    start_date: date
    end_date: date
    generated_at: datetime
    total_amount: Money | None
    record_count: int


class BillDetailOut(BillOut):
    claims: list[ClaimOut]
