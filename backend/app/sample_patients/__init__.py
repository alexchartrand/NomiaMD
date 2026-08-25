"""Synthetic demo patients loaded from consultations/, for the frontend's patient picker
and for exercising the extraction pipeline without real patient data.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service directly."""

from app.sample_patients.router import router as sample_patients_router
from app.sample_patients.service import get_sample_patient, get_sample_patients

__all__ = ["sample_patients_router", "get_sample_patient", "get_sample_patients"]
