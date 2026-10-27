"""/extract's request and response shapes."""

from datetime import date

from pydantic import BaseModel, Field

from app.care_setting import CareSetting
from app.ramq_codes import BillingCodesResult
from app.shifts import DayType, ShiftPeriod
from app.summary import ConsultationDigest


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


class RunSettingOut(BaseModel):
    """Where the run took the encounter to be (ExtractionRun's setting columns); each None
    when unknown."""

    care_setting: CareSetting | None = None
    shift_id: int | None = None
    shift_period: ShiftPeriod | None = None
    day_type: DayType | None = None


class BillingExtractionResponse(BaseModel):
    """/extract's response, and an encounter's stored run read back in the same shape
    (app/extraction/stored.py)."""

    billing: BillingCodesResult
    # What POST /claims takes: the run carries the patient and both stages' results.
    extraction_run_id: int
    encounter_date: date | None
    encounter_date_raw: str | None
    # The consultation summary as the review shows it above the codes; None for a run whose
    # summary is missing or was stored under an older schema.
    summary: ConsultationDigest | None = None
    # The setting the codes were chosen under, as the run stored it; None in POST /extract's
    # own response.
    setting: RunSettingOut | None = None
