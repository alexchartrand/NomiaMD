"""The physician's inbox over HTTP. Every route is scoped to the current user: someone
else's encounter is a 404, indistinguishable from one that doesn't exist.

The patient pick and /extract may run an extraction (the pick queues one, which runs inline
unless a worker is configured), so they don't take the per-request DbSession — they read their
response back in a fresh session_scope once the LLM calls are done. The duplicate answers
make no LLM call and use it."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import get_current_user
from app.encounters.duplicates import (
    DuplicateAlreadyBilledError,
    DuplicateDecisions,
    KeptEncounterIsDuplicateError,
    SameEncounterError,
)
from app.encounters.factory import (
    get_duplicate_decisions,
    get_encounter_removal,
    get_encounter_inbox,
    get_extraction_queue,
    get_on_demand_extraction,
)
from app.encounters.inbox import EncounterInbox
from app.encounters.models import EncounterDetailOut, EncounterRowOut, PatientPick
from app.encounters.on_demand import EncounterHasNoPatientError, OnDemandExtraction
from app.encounters.removal import EncounterHasClaimError, EncounterRemoval
from app.extraction.models import BillingExtractionResponse
from app.intake import (
    EncounterNotFoundError,
    ExtractionQueue,
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
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(get_current_user),
    inbox: EncounterInbox = Depends(get_encounter_inbox),
) -> list[EncounterRowOut]:
    """Encounters with a service date from `date_from` through `date_to` (both included,
    either optional: none at all lists every encounter). An undated one counts on the day
    it was received."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="La date de début est après la date de fin")
    return await inbox.period(current_user.id, date_from, date_to)


@router.get("/{encounter_id}", response_model=EncounterDetailOut)
async def get_encounter(
    encounter_id: int,
    current_user: User = Depends(get_current_user),
    inbox: EncounterInbox = Depends(get_encounter_inbox),
) -> EncounterDetailOut:
    detail = await inbox.detail(current_user, encounter_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return detail


@router.delete("/{encounter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_encounter(
    encounter_id: int,
    current_user: User = Depends(get_current_user),
    removal: EncounterRemoval = Depends(get_encounter_removal),
) -> Response:
    try:
        await removal.remove(encounter_id, current_user.id)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except EncounterHasClaimError as exc:
        raise HTTPException(
            status_code=409, detail="Cette rencontre est déjà facturée : supprimez d'abord sa facturation"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        detail = await EncounterInbox(session).detail(current_user, encounter_id)
    assert detail is not None
    return detail


@router.post("/{encounter_id}/extract", response_model=BillingExtractionResponse, responses={202: {"description": "Queued"}})
@limiter.limit("10/minute")
async def extract_encounter(
    request: Request,
    encounter_id: int,
    wait: bool = True,
    current_user: User = Depends(get_current_user),
    extraction: OnDemandExtraction = Depends(get_on_demand_extraction),
    queue: ExtractionQueue = Depends(get_extraction_queue),
) -> BillingExtractionResponse | Response:
    """Runs the extraction in the request and returns it; with `wait=false`, queues it for
    the background worker (202) — how a failed encounter is retried without waiting."""
    try:
        if not wait:
            await extraction.enqueue(encounter_id, current_user, queue)
            return Response(status_code=status.HTTP_202_ACCEPTED)
        return await extraction.run(encounter_id, current_user)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except EncounterHasNoPatientError as exc:
        raise HTTPException(status_code=409, detail="Associez d'abord un patient à cette rencontre") from exc


@router.post("/{encounter_id}/duplicate-of/{kept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_duplicate(
    encounter_id: int,
    kept_id: int,
    current_user: User = Depends(get_current_user),
    decisions: DuplicateDecisions = Depends(get_duplicate_decisions),
) -> Response:
    try:
        await decisions.confirm(encounter_id, kept_id, current_user.id)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except SameEncounterError as exc:
        raise HTTPException(status_code=422, detail="Une rencontre ne peut pas être son propre doublon") from exc
    except KeptEncounterIsDuplicateError as exc:
        raise HTTPException(status_code=409, detail="La rencontre à garder est elle-même un doublon") from exc
    except DuplicateAlreadyBilledError as exc:
        raise HTTPException(
            status_code=409, detail="Cette rencontre est déjà facturée : gardez-la plutôt, ou annulez sa facturation"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{encounter_id}/not-duplicate", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_duplicate(
    encounter_id: int,
    current_user: User = Depends(get_current_user),
    decisions: DuplicateDecisions = Depends(get_duplicate_decisions),
) -> Response:
    try:
        await decisions.dismiss(encounter_id, current_user.id)
    except EncounterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
