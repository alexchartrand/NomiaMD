"""Request/result shapes for the extraction pipeline — generic across every task
(billing_codes today; prescriptions, consultation notes, etc. later), not specific to any
one of them."""

from datetime import date, datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.ramq_codes import BillingCodesResult


class TranscriptSource(BaseModel):
    """Where a transcript came from, so downstream review can weigh confidence accordingly."""

    system: str = Field(description="e.g. 'epic', 'plume_ai', 'manual'")
    encounter_id: str | None = None


class ExtractionRequest(BaseModel):
    transcript: str
    task: str = Field(description="Registered task name — /extract only accepts 'billing_codes'")
    # The physician now picks the patient before extraction runs (see CLAUDE.md's
    # billing_codes pipeline description) rather than the pipeline suggesting a roster
    # match afterward — required so BillingContextBuilder always has a patient to resolve.
    patient_id: int
    source: TranscriptSource | None = None


ResultT = TypeVar("ResultT", bound=BaseModel)


class ExtractionResult(BaseModel, Generic[ResultT]):
    """Generic over the task's result type — each new task (prescriptions, consultation
    notes, ...) supplies its own result model without changing this wrapper."""

    task: str
    result: ResultT
    model: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedIdentitySummary(BaseModel):
    """What the transcript itself said about the patient (name_as_stated/
    ramq_number_as_stated/age_years, as extracted) — for display alongside the mismatch
    flags below, never used to prefill anything now that the patient is chosen up front."""

    name_as_stated: str | None
    ramq_number_as_stated: str | None
    age_years: float | None


class PatientVerificationOut(BaseModel):
    """Each `*_mismatch` is null when the transcript didn't state enough to compare, and a
    bool otherwise — a safety-net warning, not a gate: the physician already chose this
    patient before extraction ran (see ExtractionRequest.patient_id)."""

    extracted: ExtractedIdentitySummary
    nam_mismatch: bool | None
    name_mismatch: bool | None
    age_mismatch: bool | None


class BillingExtractionResponse(BaseModel):
    """/extract's response — a wrapper around the generic ExtractionResult rather than
    extra sibling fields on it directly, since that envelope is documented as generic over
    any task's result type and hanging billing-specific pipeline output off it would break
    the contract for every future task."""

    billing: ExtractionResult[BillingCodesResult]
    summary_extraction_record_id: int
    billing_extraction_record_id: int
    encounter_date: date | None
    encounter_date_raw: str | None
    patient_verification: PatientVerificationOut | None
