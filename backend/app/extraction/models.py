"""/extract's request and response shapes."""

from datetime import date

from pydantic import BaseModel, Field

from app.ramq_codes import BillingCodesResult


class TranscriptSource(BaseModel):
    """Where a transcript came from, so downstream review can weigh confidence accordingly."""

    system: str = Field(description="e.g. 'epic', 'plume_ai', 'manual'")
    encounter_id: str | None = None


class ExtractionRequest(BaseModel):
    transcript: str
    # The physician now picks the patient before extraction runs (see CLAUDE.md's
    # billing_codes pipeline description) rather than the pipeline suggesting a roster
    # match afterward — required so BillingContextBuilder always has a patient to resolve.
    patient_id: int
    source: TranscriptSource | None = None


class BillingExtractionResponse(BaseModel):
    """/extract's response, and an encounter's stored run read back in the same shape
    (app/extraction/stored.py)."""

    billing: BillingCodesResult
    # What POST /claims takes: the run carries the patient and both stages' results.
    extraction_run_id: int
    encounter_date: date | None
    encounter_date_raw: str | None
