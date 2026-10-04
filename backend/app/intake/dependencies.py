"""FastAPI glue for the intake routes. The IntakeService itself is built once, at startup, by
app/main.py's lifespan: its queue runs the billing pipeline, which the intake context never
imports (see app/intake/queue.py)."""

from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.intake.connectors import ManualConnector, PullConnector
from app.intake.connectors.epic_fhir import SandboxRoster
from app.intake.connectors.epic_fhir.factory import sandbox_connector
from app.intake.service import IntakeService

_EPIC_TIMEOUT_SECONDS = 30


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_manual_connector() -> ManualConnector:
    return ManualConnector()


def require_epic_sandbox() -> None:
    """The sandbox routes don't exist unless EPIC_SANDBOX_ENABLED is on."""
    if not settings.epic_sandbox_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


def get_epic_sandbox_roster() -> SandboxRoster:
    return SandboxRoster.load()


async def get_epic_sandbox_connector(
    roster: SandboxRoster = Depends(get_epic_sandbox_roster),
) -> AsyncIterator[PullConnector]:
    # One HTTP client (and one access token) per import.
    async with httpx.AsyncClient(timeout=_EPIC_TIMEOUT_SECONDS) as http:
        yield sandbox_connector(http, settings, roster)
