"""Claim request/response models — same style as app/patients/models.py."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

# "brouillon" -> "soumis" -> "facture". "soumis" is set only by BillService.create when a
# claim is grouped onto a generated bill; "facture" is reserved for a future real RAMQ
# submission response and nothing in this codebase sets it yet. Status is otherwise
# read-only from the API's perspective — there is no PATCH endpoint for it.
ClaimStatus = Literal["brouillon", "soumis", "facture"]

# Mirrors app/ramq_codes/models.py's ExtractedCode.confidence — defined locally rather than
# imported, same "claims reads the extraction's own stored JSON blob, it doesn't share types
# with ramq_codes" boundary as ClaimService's docstring describes.
ConfidenceLevel = Literal["high", "medium", "low"]

# Decimal internally (exact storage/arithmetic), plain float on the JSON wire — the
# frontend's `number` fields and its own display-only .toFixed(2) calls are unaffected.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ClaimCreate(BaseModel):
    patient_id: int
    service_date: date
    billing_extraction_record_id: int
    summary_extraction_record_id: int | None = None
    selected_codes: list[str]
    source_system: str | None = None


class ClaimCodeOut(BaseModel):
    code: str
    description: str
    confidence: ConfidenceLevel
    explanation: str
    fee_amount: Money | None
    fee_when_to_use: str | None
    majoration: str | None

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: int
    patient_id: int
    patient_full_name: str
    service_date: date
    status: ClaimStatus
    source_system: str | None
    codes: list[ClaimCodeOut]
    total_amount: Money | None
    created_at: datetime
    updated_at: datetime
