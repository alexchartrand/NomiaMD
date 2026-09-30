from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.patients.factory import get_patient_repository, get_patient_search, get_roster_repository
from app.patients.models import (
    PatientCreate,
    PatientOut,
    PatientUpdate,
    RosterEntryCreate,
    RosterEntryOut,
    RosterEntryUpdate,
)
from app.patients.registration import resolve_registration
from app.patients.search import PatientSearch
from app.postgresdb import (
    DuplicatePatientRamqNumberError,
    DuplicateRosterEntryError,
    Patient,
    PatientRepository,
    PhysicianPatient,
    PhysicianPatientRepository,
    User,
    UserRole,
)

router = APIRouter(prefix="/patients", tags=["patients"])


def _duplicate_ramq_number_detail(exc: DuplicatePatientRamqNumberError) -> str:
    return f"Un autre patient actif porte déjà le NAM {exc.ramq_number}"


def _to_patient_out(patient: Patient, *, current_user: User) -> PatientOut:
    return PatientOut.model_validate(patient).model_copy(
        update={
            "is_registered_with_current_physician": resolve_registration(
                patient.family_doctor_practice_number, current_user.practice_number
            )
        }
    )


def _to_roster_entry_out(entry: PhysicianPatient, patient: Patient, *, current_user: User) -> RosterEntryOut:
    patient_out = _to_patient_out(patient, current_user=current_user)
    return RosterEntryOut(**patient_out.model_dump(), notes=entry.notes)


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")


@router.get("", response_model=list[RosterEntryOut])
async def list_roster(
    current_user: User = Depends(get_current_user),
    roster: PhysicianPatientRepository = Depends(get_roster_repository),
) -> list[RosterEntryOut]:
    rows = await roster.list_roster(current_user.id)
    return [_to_roster_entry_out(entry, patient, current_user=current_user) for entry, patient in rows]


@router.get("/search", response_model=list[PatientOut])
async def search_patients(
    q: str = Query(min_length=1),
    current_user: User = Depends(get_current_user),
    patient_search: PatientSearch = Depends(get_patient_search),
) -> list[PatientOut]:
    matches = await patient_search.search(q)
    return [_to_patient_out(p, current_user=current_user) for p in matches]


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    body: PatientCreate,
    current_user: User = Depends(get_current_user),
    patients: PatientRepository = Depends(get_patient_repository),
) -> PatientOut:
    try:
        patient = await patients.create(**body.model_dump())
    except DuplicatePatientRamqNumberError as exc:
        raise HTTPException(status_code=409, detail=_duplicate_ramq_number_detail(exc)) from exc
    return _to_patient_out(patient, current_user=current_user)


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    patients: PatientRepository = Depends(get_patient_repository),
) -> PatientOut:
    patient = await patients.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    return _to_patient_out(patient, current_user=current_user)


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: int,
    body: PatientUpdate,
    current_user: User = Depends(get_current_user),
    patients: PatientRepository = Depends(get_patient_repository),
) -> PatientOut:
    # Patient is a shared, global record now — only admins may edit its demographic/
    # administrative fields, since any physician editing another physician's patient's
    # data has no ownership check left to gate it (see the plan's edit-authorization note).
    _require_admin(current_user)
    try:
        patient = await patients.update(patient_id, **body.model_dump())
    except DuplicatePatientRamqNumberError as exc:
        raise HTTPException(status_code=409, detail=_duplicate_ramq_number_detail(exc)) from exc
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    return _to_patient_out(patient, current_user=current_user)


@router.post("/roster", response_model=RosterEntryOut, status_code=status.HTTP_201_CREATED)
async def add_to_roster(
    body: RosterEntryCreate,
    current_user: User = Depends(get_current_user),
    patients: PatientRepository = Depends(get_patient_repository),
    roster: PhysicianPatientRepository = Depends(get_roster_repository),
) -> RosterEntryOut:
    patient = await patients.get(body.patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    try:
        entry = await roster.add(current_user.id, body.patient_id, notes=body.notes)
    except DuplicateRosterEntryError as exc:
        raise HTTPException(
            status_code=409, detail="Ce patient est déjà dans votre liste"
        ) from exc
    return _to_roster_entry_out(entry, patient, current_user=current_user)


@router.patch("/roster/{patient_id}", response_model=RosterEntryOut)
async def update_roster_entry(
    patient_id: int,
    body: RosterEntryUpdate,
    current_user: User = Depends(get_current_user),
    patients: PatientRepository = Depends(get_patient_repository),
    roster: PhysicianPatientRepository = Depends(get_roster_repository),
) -> RosterEntryOut:
    entry = await roster.update(current_user.id, patient_id, notes=body.notes)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient absent de votre liste")
    patient = await patients.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable")
    return _to_roster_entry_out(entry, patient, current_user=current_user)


@router.delete("/roster/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_roster(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    roster: PhysicianPatientRepository = Depends(get_roster_repository),
) -> None:
    removed = await roster.remove(current_user.id, patient_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient absent de votre liste")
