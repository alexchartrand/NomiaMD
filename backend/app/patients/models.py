"""Patient request/response models — same style as app/auth/models.py."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.patients import nam
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

    @field_validator("ramq_number", mode="before")
    @classmethod
    def _canonical_nam(cls, value: str | None) -> str | None:
        # Stored canonical (4 uppercase letters + 8 digits, no spacing) so the global
        # one-patient-per-NAM unique index sees "desr 8102 1001" and "DESR81021001" as the
        # same person. Blank means "no NAM on file", same as null.
        if value is None or not value.strip():
            return None
        normalized = nam.normalize(value)
        if normalized is None:
            raise ValueError("NAM invalide : 4 lettres suivies de 8 chiffres attendues")
        return normalized


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
