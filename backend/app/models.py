"""Shared Pydantic models for extraction requests and results."""

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


class TranscriptSource(BaseModel):
    """Where a transcript came from, so downstream review can weigh confidence accordingly."""

    system: str = Field(description="e.g. 'epic', 'plume_ai', 'manual'")
    encounter_id: str | None = None


class ExtractionRequest(BaseModel):
    transcript: str
    task: str = Field(description="Registered task name, e.g. 'billing_codes'")
    source: TranscriptSource | None = None


class SamplePatientSummary(BaseModel):
    """One entry in the patient-selection dropdown."""

    id: str
    label: str


class SamplePatientDetail(SamplePatientSummary):
    transcript: str


class ExtractedCode(BaseModel):
    code: str = Field(description="RAMQ code as it appears in the reference table")
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_quote: str = Field(
        description=(
            "Short verbatim excerpt from the consultation summary (not the raw transcript) "
            "that justifies this code"
        )
    )


class BillingCodesResult(BaseModel):
    codes: list[ExtractedCode]
    notes: str | None = Field(
        default=None,
        description="Anything the model flagged as ambiguous or needing physician review",
    )


ResultT = TypeVar("ResultT", bound=BaseModel)


class ExtractionResult(BaseModel, Generic[ResultT]):
    """Generic over the task's result type — each new task (prescriptions, consultation
    notes, ...) supplies its own result model without changing this wrapper."""

    task: str
    result: ResultT
    model: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
