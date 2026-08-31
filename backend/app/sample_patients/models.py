"""API-response shapes for the sample-patient endpoints. See .service's SamplePatient
dataclass for the underlying data these are built from."""

from pydantic import BaseModel


class SamplePatientSummary(BaseModel):
    """One entry in the patient-selection dropdown."""

    id: str
    label: str


class SamplePatientDetail(SamplePatientSummary):
    transcript: str
    # Normalized NAM, when the note's header has one — lets the frontend look up the
    # matching real Patient row (seeded by scripts/seed_db.py) and auto-fill it.
    nam: str | None
