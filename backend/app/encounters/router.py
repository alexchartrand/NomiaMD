"""The physician's inbox over HTTP. Every route is scoped to the current user: someone
else's encounter is a 404, indistinguishable from one that doesn't exist.

The two POST routes may run an extraction (the patient pick queues one, which runs inline
until step 10's worker), so they don't take the per-request DbSession — they read their
response back in a fresh session_scope once the LLM calls are done."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import get_current_user
from app.clock import Clock, get_clock
from app.encounters.factory import get_encounter_inbox, get_on_demand_extraction
from app.encounters.inbox import EncounterInbox
from app.encounters.models import EncounterDetailOut, EncounterRowOut, PatientPick
from app.encounters.on_demand import EncounterHasNoPatientError, OnDemandExtraction
from app.extraction.models import BillingExtractionResponse
from app.intake import (
    EncounterNotFoundError,
    IntakeService,
    PatientAlreadyAssignedError,
    PatientNotFoundError,
)
from app.intake.dependencies import get_intake_service
from app.postgresdb import User, session_scope
from app.rate_limit import limiter

router = APIRouter(prefix="/encounters", tags=["encounters"])

_NOT_FOUND = "Rencontre introuvable"


@router.get("", response_model=list[EncounterRowOut])
async def list_encounters(
    day: date | None = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user),
    inbox: EncounterInbox = Depends(get_encounter_inbox),
    clock: Clock = Depends(get_clock),
) -> list[EncounterRowOut]:
    return await inbox.day(current_user.id, day or clock.today())


@router.get("/{encounter_id}", response_model=EncounterDetailOut)
async def get_encounter(
    encounter_id: int,
    current_user: User = Depends(get_current_user),
    inbox: EncounterInbox = Depends(get_encounter_inbox),
) -> EncounterDetailOut:
    detail = await inbox.detail(current_user.id, encounter_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return detail


@router.post("/{encounter_id}/patient", response_model=EncounterDetailOut)
@limiter.limit("10/minute")
async def assign_patient(
    request: Request,
    encounter_id: int,
    body: PatientPick,
    current_user: User = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
) -> EncounterDetailOut:
    try:
        await service.assign_patient(encounter_id, body.patient_id, current_user)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Patient introuvable") from exc
    except PatientAlreadyAssignedError as exc:
        raise HTTPException(status_code=409, detail="Cette rencontre est déjà associée à un patient") from exc
    async with session_scope() as session:
        detail = await EncounterInbox(session).detail(current_user.id, encounter_id)
    assert detail is not None
    return detail


@router.post("/{encounter_id}/extract", response_model=BillingExtractionResponse)
@limiter.limit("10/minute")
async def extract_encounter(
    request: Request,
    encounter_id: int,
    current_user: User = Depends(get_current_user),
    extraction: OnDemandExtraction = Depends(get_on_demand_extraction),
) -> BillingExtractionResponse:
    try:
        return await extraction.run(encounter_id, current_user)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except EncounterHasNoPatientError as exc:
        raise HTTPException(status_code=409, detail="Associez d'abord un patient à cette rencontre") from exc
