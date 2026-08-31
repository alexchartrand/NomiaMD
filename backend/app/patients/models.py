"""Patient request/response models — same style as app/auth/models.py."""

from datetime import date

from pydantic import BaseModel, Field

from app.postgresdb import Gender

_PRACTICE_NUMBER_PATTERN = r"^\d{5,6}$"


class PatientBase(BaseModel):
    full_name: str
    ramq_number: str | None = None
    date_of_birth: date
    gender: Gender | None = None
    is_vulnerable: bool = False
    family_doctor_name: str | None = None
    family_doctor_practice_number: str | None = Field(default=None, pattern=_PRACTICE_NUMBER_PATTERN)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(PatientBase):
    pass


class PatientOut(PatientBase):
    id: int
    # Read-only and request-relative: computed by the router from the requesting
    # physician's own practice_number, never stored — see app/patients/registration.py.
    is_registered_with_current_physician: bool | None = None

    model_config = {"from_attributes": True}


class RosterEntryCreate(BaseModel):
    patient_id: int
    notes: str | None = None


class RosterEntryUpdate(BaseModel):
    notes: str | None = None


class RosterEntryOut(PatientOut):
    notes: str | None = None
