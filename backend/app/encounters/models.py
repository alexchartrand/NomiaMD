"""Response shapes for /encounters. Mirrored by hand in frontend/src/api/encounters.ts."""

from datetime import date, datetime

from pydantic import BaseModel

from app.claims.models import ClaimOut
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
    # The codes billed on its live claim once there is one (status "revu"), else the codes
    # the latest run proposes; None when it was never extracted.
    code_count: int | None
    # The latest run (what POST /claims takes); None when it was never extracted.
    extraction_run_id: int | None
    # "Doublon possible": the day's other encounters this may be the same visit as, until
    # the physician answers (see app/encounters/duplicates.py).
    possible_duplicate_ids: list[int]
    # Approvable without opening it: see app/encounters/readiness.py.
    all_clean: bool
    # Deletable: no live claim (see app/encounters/removal.py).
    deletable: bool


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
    # Set once the physician confirmed it's the same visit as that encounter.
    duplicate_of_id: int | None
    note_text: str
    extraction_error: str | None
    extraction: BillingExtractionResponse | None
    # The live claim saved from one of its runs: the codes the physician selected.
    claim: ClaimOut | None


class PatientPick(BaseModel):
    patient_id: int
