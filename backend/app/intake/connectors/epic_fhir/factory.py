"""Builds the sandbox connector from settings — the one place that reads EPIC_SANDBOX_*."""

import httpx

from app.config import Settings
from app.intake.connectors.epic_fhir.auth import BackendServicesTokenProvider
from app.intake.connectors.epic_fhir.client import EpicFhirClient
from app.intake.connectors.epic_fhir.identifiers import SandboxIdentifierStrategy
from app.intake.connectors.epic_fhir.mapper import EpicNoteMapper
from app.intake.connectors.epic_fhir.reader import EpicNoteReader
from app.intake.connectors.epic_fhir.sandbox import (
    EPIC_SANDBOX_SOURCE_SYSTEM,
    EpicSandboxConnector,
    ensure_sandbox_allowed,
)
from app.intake.connectors.epic_fhir.sandbox_roster import SandboxRoster


def sandbox_client(http: httpx.AsyncClient, settings: Settings) -> EpicFhirClient:
    tokens = BackendServicesTokenProvider(
        http,
        token_url=settings.epic_sandbox_token_url,
        client_id=settings.epic_sandbox_client_id,
        private_key_pem=settings.epic_sandbox_private_key_path.read_text(encoding="utf-8"),
        key_id=settings.epic_sandbox_key_id,
    )
    return EpicFhirClient(http, settings.epic_sandbox_fhir_base_url, tokens)


def sandbox_connector(http: httpx.AsyncClient, settings: Settings, roster: SandboxRoster) -> EpicSandboxConnector:
    mapper = EpicNoteMapper(SandboxIdentifierStrategy(roster), EPIC_SANDBOX_SOURCE_SYSTEM)
    return EpicSandboxConnector(EpicNoteReader(sandbox_client(http, settings), mapper), roster)


def check_sandbox_startup(settings: Settings) -> None:
    """Fails the boot, not the first import: the flag on in production, or on without a
    client id or key file."""
    ensure_sandbox_allowed(settings.epic_sandbox_enabled, settings.app_env)
    if not settings.epic_sandbox_enabled:
        return
    settings.epic_sandbox_client_id
    if not settings.epic_sandbox_private_key_path.is_file():
        raise FileNotFoundError(f"EPIC_SANDBOX_PRIVATE_KEY_PATH: no file at {settings.epic_sandbox_private_key_path}")
