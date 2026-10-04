"""The Epic sandbox demo (step 11b): pull the synthetic sandbox patients' signed notes into
the inbox. Every route is 404 unless EPIC_SANDBOX_ENABLED is on, and startup refuses the
flag in production (app/intake/connectors/epic_fhir/factory.py).

Not on the per-request DbSession, for the same reason as app/intake/router.py."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.intake.connectors import PullConnector
from app.intake.connectors.epic_fhir import EpicFhirError, SandboxRoster
from app.intake.dependencies import (
    get_epic_sandbox_connector,
    get_epic_sandbox_roster,
    get_intake_service,
    require_epic_sandbox,
)
from app.intake.models import EpicSandboxStatus, ReceiveOutcomeOut
from app.intake.router import receive_and_report
from app.intake.service import IntakeService
from app.postgresdb import User
from app.rate_limit import limiter

router = APIRouter(prefix="/intake/epic-sandbox", tags=["intake"], dependencies=[Depends(require_epic_sandbox)])


@router.get("", response_model=EpicSandboxStatus)
async def epic_sandbox_status(
    current_user: User = Depends(get_current_user),
    roster: SandboxRoster = Depends(get_epic_sandbox_roster),
) -> EpicSandboxStatus:
    """Tells the frontend the demo is on (it's a 404 otherwise)."""
    return EpicSandboxStatus(patients=len(roster))


@router.post("/import", response_model=list[ReceiveOutcomeOut])
@limiter.limit("5/minute")
async def import_epic_sandbox(
    request: Request,
    current_user: User = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
    connector: PullConnector = Depends(get_epic_sandbox_connector),
) -> list[ReceiveOutcomeOut]:
    """Every signed note of the roster's patients. Importing again stores nothing new: the
    notes come back as duplicates (same DocumentReference id and content)."""
    try:
        notes = await connector.fetch_signed_notes(current_user)
    except EpicFhirError as exc:
        raise HTTPException(status_code=502, detail="Le bac à sable Epic n'a pas répondu correctement") from exc
    if not notes:
        return []
    return await receive_and_report(service, notes, current_user)
