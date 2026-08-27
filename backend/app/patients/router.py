from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.patients.models import PatientCreate, PatientOut, PatientUpdate
from app.postgresdb import DuplicatePatientRamqNumberError, Patient, PatientRepository, User

router = APIRouter(prefix="/patients", tags=["patients"])


def _duplicate_ramq_number_detail(exc: DuplicatePatientRamqNumberError) -> str:
    return f"Un autre patient actif porte déjà le NAM {exc.ramq_number}"


@router.get("", response_model=list[PatientOut])
async def list_patients(current_user: User = Depends(get_current_user)) -> list[Patient]:
    return list(await PatientRepository().list_for_physician(current_user.id))


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(body: PatientCreate, current_user: User = Depends(get_current_user)) -> Patient:
    try:
        return await PatientRepository().create(physician_id=current_user.id, **body.model_dump())
    except DuplicatePatientRamqNumberError as exc:
        raise HTTPException(status_code=409, detail=_duplicate_ramq_number_detail(exc)) from exc


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: int, current_user: User = Depends(get_current_user)) -> Patient:
    patient = await PatientRepository().get_for_physician(patient_id, current_user.id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: int, body: PatientUpdate, current_user: User = Depends(get_current_user)
) -> Patient:
    try:
        patient = await PatientRepository().update_for_physician(
            patient_id, current_user.id, **body.model_dump()
        )
    except DuplicatePatientRamqNumberError as exc:
        raise HTTPException(status_code=409, detail=_duplicate_ramq_number_detail(exc)) from exc
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(patient_id: int, current_user: User = Depends(get_current_user)) -> None:
    deleted = await PatientRepository().delete_for_physician(patient_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
