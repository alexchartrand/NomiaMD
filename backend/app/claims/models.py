"""Claim request/response models — same style as app/patients/models.py."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

from app.claims.status import ClaimStatus
from app.ramq_codes import FeeUnit


# Mirrors app/ramq_codes/models.py's ExtractedCode.confidence — defined locally rather than
# imported, same "claims reads the extraction's own stored JSON blob, it doesn't share types
# with ramq_codes" boundary as ClaimService's docstring describes.
ConfidenceLevel = Literal["high", "medium", "low"]

# Decimal internally (exact storage/arithmetic), plain float on the JSON wire — the
# frontend's `number` fields and its own display-only .toFixed(2) calls are unaffected.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class SelectedCode(BaseModel):
    """One code the physician chose to bill, plus which of that code's resolved fee
    variants applies — an index into ExtractedCode.fees rather than a fee ID, since a
    resolved fee has no stable identity of its own. None defaults to the first (and, for a
    single-fee code, only) entry server-side."""

    code: str
    fee_index: int | None = None


class ClaimCreate(BaseModel):
    """No patient_id or source_system: both come from the extraction run, whose codes were
    eligibility-filtered for that patient. service_date stays — the physician may correct
    the encounter date the extraction parsed."""

    extraction_run_id: int
    service_date: date
    selected_codes: list[SelectedCode]


class ClaimCodeOut(BaseModel):
    code: str
    description: str
    confidence: ConfidenceLevel
    explanation: str
    # Dollars only — a fee in units carries its count in fee_units instead.
    fee_amount: Money | None
    fee_unit: FeeUnit | None
    fee_units: Money | None
    fee_role: int | None
    fee_context: str | None
    fee_lieux: list[str] | None
    majoration: str | None
    manual_rev: str | None

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: int
    patient_id: int
    patient_full_name: str
    service_date: date
    # Derived from bill_id — see app/claims/status.py.
    status: ClaimStatus
    bill_id: int | None
    source_system: str | None
    codes: list[ClaimCodeOut]
    total_amount: Money | None
    created_at: datetime
    updated_at: datetime
