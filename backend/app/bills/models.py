"""Bill request/response models — same style as app/billing/models.py."""

from datetime import date, datetime

from pydantic import BaseModel

from app.billing.models import BillingRecordOut


class BillCreate(BaseModel):
    start_date: date
    end_date: date
    billing_record_ids: list[int]


class BillOut(BaseModel):
    id: int
    number: str
    start_date: date
    end_date: date
    generated_at: datetime
    total_amount: float | None
    record_count: int


class BillDetailOut(BillOut):
    records: list[BillingRecordOut]
