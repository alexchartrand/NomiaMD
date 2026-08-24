"""CRUD for a physician's own patient roster, plus NAM-based identification of a roster
patient from an LLM-extracted identity (see .nam, .suggestion).

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.nam/.suggestion directly."""

from app.patients import nam
from app.patients.router import router as patients_router
from app.patients.suggestion import (
    ExtractedIdentity,
    PatientPrefill,
    PatientSuggestion,
    PatientSuggestionService,
)

__all__ = [
    "patients_router",
    "nam",
    "ExtractedIdentity",
    "PatientPrefill",
    "PatientSuggestion",
    "PatientSuggestionService",
]
