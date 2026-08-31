"""Global patient identity CRUD/search, a physician's own optional "my patients" roster,
NAM parsing (.nam), derived registration status (.registration), and verification of a
transcript's stated identity against the patient chosen before extraction (.verification).

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.nam/.registration/.verification directly."""

from app.patients import nam
from app.patients.name_format import format_full_name
from app.patients.registration import resolve_registration
from app.patients.router import router as patients_router
from app.patients.verification import (
    ExtractedIdentity,
    PatientVerification,
    verify_patient_identity,
)

__all__ = [
    "patients_router",
    "nam",
    "format_full_name",
    "resolve_registration",
    "ExtractedIdentity",
    "PatientVerification",
    "verify_patient_identity",
]
