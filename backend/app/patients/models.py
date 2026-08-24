"""Patient request/response models — same style as app/auth/models.py."""

from datetime import date

from pydantic import BaseModel

from app.postgresdb import Gender


class PatientBase(BaseModel):
    full_name: str
    ramq_number: str | None = None
    date_of_birth: date
    gender: Gender | None = None
    is_registered_with_physician: bool = False
    is_vulnerable: bool = False


class PatientCreate(PatientBase):
    pass


class PatientUpdate(PatientBase):
    pass


class PatientOut(PatientBase):
    id: int

    model_config = {"from_attributes": True}
