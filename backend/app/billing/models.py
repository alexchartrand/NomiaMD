"""Billing request/response models — same style as app/patients/models.py."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

BillingStatus = Literal["brouillon", "facture"]


class BillingRecordCreate(BaseModel):
    patient_id: int
    service_date: date
    billing_extraction_record_id: int
    summary_extraction_record_id: int | None = None
    selected_codes: list[str]
    source_system: str | None = None


class BillingStatusUpdate(BaseModel):
    status: BillingStatus


class BillingRecordCodeOut(BaseModel):
    code: str
    description: str
    confidence: float
    supporting_quote: str
    fee_amount: float | None
    fee_when_to_use: str | None
    majoration: str | None

    model_config = {"from_attributes": True}


class BillingRecordOut(BaseModel):
    id: int
    patient_id: int
    patient_full_name: str
    service_date: date
    status: BillingStatus
    source_system: str | None
    codes: list[BillingRecordCodeOut]
    total_amount: float | None
    created_at: datetime
    updated_at: datetime
