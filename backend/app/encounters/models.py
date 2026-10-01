"""Response shapes for /encounters. Mirrored by hand in frontend/src/api/encounters.ts."""

from datetime import date, datetime

from pydantic import BaseModel

from app.extraction.models import BillingExtractionResponse
from app.intake import EncounterStatus


class MaskedPatientOut(BaseModel):
    """Enough for the physician to recognize the patient in a list seen over a shoulder —
    the detail view shows the rest."""

    id: int
    display_name: str
    nam: str | None


class PatientOut(BaseModel):
    id: int
    full_name: str
    nam: str | None


class EncounterRowOut(BaseModel):
    id: int
    status: EncounterStatus
    patient: MaskedPatientOut | None
    source_system: str
    channel: str
    batch_label: str | None
    service_date: date | None
    received_at: datetime
    # Codes in the latest run; None when it was never extracted.
    code_count: int | None
    # Approvable without opening it: see app/encounters/readiness.py.
    all_clean: bool


class EncounterDetailOut(BaseModel):
    id: int
    status: EncounterStatus
    patient: PatientOut | None
    source_system: str
    channel: str
    external_note_id: str | None
    external_encounter_id: str | None
    batch_label: str | None
    service_date: date | None
    received_at: datetime
    meta: dict
    note_text: str
    extraction_error: str | None
    extraction: BillingExtractionResponse | None


class PatientPick(BaseModel):
    patient_id: int
