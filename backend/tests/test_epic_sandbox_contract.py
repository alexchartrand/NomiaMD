"""Contract test against the live Epic sandbox (fhir.epic.com): the real token exchange, a
real search and the mapper on what really comes back. Excluded from the default run — opt in
with `uv run pytest -m epic_sandbox`, with EPIC_SANDBOX_CLIENT_ID and
EPIC_SANDBOX_PRIVATE_KEY_PATH set (backend/.env is read)."""

import os

import httpx
import pytest

from app.config import settings
from app.intake.connectors.epic_fhir import SandboxRoster
from app.intake.connectors.epic_fhir.factory import sandbox_client, sandbox_connector
from tests.db_helpers import physician

pytestmark = pytest.mark.epic_sandbox

# Read at import, before conftest's no_real_api_keys clears them for every test.
_CREDENTIALS = {
    name: os.environ.get(name)
    for name in ("EPIC_SANDBOX_CLIENT_ID", "EPIC_SANDBOX_PRIVATE_KEY_PATH", "EPIC_SANDBOX_KEY_ID")
}


@pytest.fixture(autouse=True)
def sandbox_credentials(monkeypatch):
    if not (_CREDENTIALS["EPIC_SANDBOX_CLIENT_ID"] and _CREDENTIALS["EPIC_SANDBOX_PRIVATE_KEY_PATH"]):
        pytest.skip("EPIC_SANDBOX_CLIENT_ID / EPIC_SANDBOX_PRIVATE_KEY_PATH not set")
    for name, value in _CREDENTIALS.items():
        if value:
            monkeypatch.setenv(name, value)


async def test_the_sandbox_issues_a_token_and_answers_a_search():
    roster = SandboxRoster.load()
    if len(roster) == 0:
        pytest.skip("empty roster — run scripts/epic_sandbox_inventory.py --write first")
    patient = roster.patients()[0]

    async with httpx.AsyncClient(timeout=30) as http:
        documents = await sandbox_client(http, settings).search(
            "DocumentReference", {"patient": patient.fhir_id, "category": "clinical-note"}
        )

    assert all(document["resourceType"] == "DocumentReference" for document in documents)


async def test_every_roster_note_still_comes_back_and_maps():
    roster = SandboxRoster.load()
    if len(roster) == 0:
        pytest.skip("empty roster — run scripts/epic_sandbox_inventory.py --write first")

    async with httpx.AsyncClient(timeout=30) as http:
        notes = await sandbox_connector(http, settings, roster).fetch_signed_notes(physician(1))

    # A listed note gone from the sandbox (or no longer signed) would quietly thin the demo.
    assert {note.external_note_id for note in notes} == {
        note_id for patient in roster.patients() for note_id in patient.note_ids
    }
    assert {note.nam for note in notes} == {patient.nam for patient in roster.patients()}
    assert all(note.text.strip() and note.external_note_id for note in notes)
