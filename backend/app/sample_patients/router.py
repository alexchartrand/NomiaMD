from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.sample_patients.models import SamplePatientDetail, SamplePatientSummary
from app.sample_patients.service import get_sample_patient, get_sample_patients

router = APIRouter(prefix="/sample-patients", tags=["sample-patients"])


@router.get("", response_model=list[SamplePatientSummary], dependencies=[Depends(get_current_user)])
# Lists the synthetic demo patients from consultations/, for the frontend's patient picker.
def list_sample_patients() -> list[SamplePatientSummary]:
    return [SamplePatientSummary(id=p.id, label=p.label) for p in get_sample_patients()]


@router.get(
    "/{patient_id}",
    response_model=SamplePatientDetail,
    dependencies=[Depends(get_current_user)],
)
# Fetches one demo patient's full transcript by id; 404 if the id doesn't match a file in consultations/.
def get_sample_patient_by_id(patient_id: str) -> SamplePatientDetail:
    patient = get_sample_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"No sample patient with id '{patient_id}'")
    return SamplePatientDetail(id=patient.id, label=patient.label, transcript=patient.transcript)
