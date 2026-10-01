"""Where notes are pushed in over HTTP: pasted text or a list of structured SourceNotes
(`/intake/notes`), or an uploaded text file (`/intake/upload`). Session auth for now — step
12 adds device tokens for the extension, step 15 HMAC for scribes.

Deliberately not on the per-request DbSession: IntakeService opens its own short sessions,
and its queue may run the extraction inline, whose LLM calls must not hold a pooled
connection (same reasoning as POST /extract)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.auth import get_current_user
from app.intake.connectors import ManualConnector, UnsupportedUploadError
from app.intake.dependencies import get_intake_service, get_manual_connector
from app.intake.models import PastedNotes, ReceiveOutcomeOut, SourceNote
from app.intake.service import EmptyNoteError, IntakeService, ReceiveOutcome
from app.postgresdb import User
from app.rate_limit import limiter

router = APIRouter(prefix="/intake", tags=["intake"])

# A whole ER shift of notes is a few hundred KB at most.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@router.post("/notes", response_model=list[ReceiveOutcomeOut])
@limiter.limit("10/minute")
async def receive_notes(
    request: Request,
    body: PastedNotes | list[SourceNote],
    current_user: User = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
    connector: ManualConnector = Depends(get_manual_connector),
) -> list[ReceiveOutcomeOut]:
    notes = (
        connector.from_paste(body.text, body.source_system, body.batch_label) if isinstance(body, PastedNotes) else body
    )
    return await _receive(service, notes, current_user)


@router.post("/upload", response_model=list[ReceiveOutcomeOut])
@limiter.limit("10/minute")
async def upload_notes(
    request: Request,
    file: UploadFile = File(...),
    source_system: str = Form(default="manual", min_length=1, max_length=64),
    batch_label: str | None = Form(default=None, max_length=64),
    current_user: User = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
    connector: ManualConnector = Depends(get_manual_connector),
) -> list[ReceiveOutcomeOut]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (2 Mo maximum)")
    try:
        notes = connector.from_upload(file.filename or "", content, source_system, batch_label)
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _receive(service, notes, current_user)


async def _receive(service: IntakeService, notes: list[SourceNote], user: User) -> list[ReceiveOutcomeOut]:
    if not notes:
        raise HTTPException(status_code=422, detail="Aucune note à recevoir")
    try:
        outcomes = await service.receive_all(notes, user)
    except EmptyNoteError as exc:
        # Notes before it are already stored; resending the corrected batch is safe, since
        # those come back as duplicates.
        raise HTTPException(status_code=422, detail="Une note est vide une fois nettoyée") from exc
    return [_out(outcome) for outcome in outcomes]


def _out(outcome: ReceiveOutcome) -> ReceiveOutcomeOut:
    return ReceiveOutcomeOut(
        outcome=outcome.outcome,
        encounter_id=outcome.encounter_id,
        patient_id=outcome.patient_id,
        enqueued=outcome.enqueued,
    )
