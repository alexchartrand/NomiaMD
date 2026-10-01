"""Global patient identity CRUD/search, a physician's own optional "my patients" roster,
NAM parsing (.nam), and derived registration status (.registration).

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.nam/.registration directly."""

from app.patients import nam
from app.patients.name_format import format_full_name
from app.patients.registration import resolve_registration
from app.patients.router import router as patients_router

__all__ = [
    "patients_router",
    "nam",
    "format_full_name",
    "resolve_registration",
]
