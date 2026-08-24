"""API-response shapes for the sample-patient endpoints (app/main.py's /sample-patients,
/sample-patients/{id}). Not colocated in a feature folder like app/extraction/models.py:
app/sample_patients.py is a flat module, not a package — see its own SamplePatient
dataclass for the underlying data these are built from."""

from pydantic import BaseModel


class SamplePatientSummary(BaseModel):
    """One entry in the patient-selection dropdown."""

    id: str
    label: str


class SamplePatientDetail(SamplePatientSummary):
    transcript: str
