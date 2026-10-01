"""The intake and inbox routes over HTTP (step 09): pushing notes in (/intake/notes,
/intake/upload) and working the inbox (/encounters...). The billing pipeline runs for real
against the mocked model (two chat calls per extraction) and conftest's stub retriever.

Each test acts as its own physician, so the inbox only ever holds that test's encounters.
Seeds through session_scope (committed): the routes open their own sessions."""

import itertools
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import get_current_user
from app.clock import ClinicClock, get_clock
from app.encounters.masking import mask_name, mask_nam
from app.main import app
from app.postgresdb import Encounter, ExtractionRun, Gender, PatientRepository, session_scope
from tests.db_helpers import ensure_user_row, physician
from tests.test_extraction import MOCK_RESULT, MOCK_SUMMARY_RESULT, _mock_response

_physician_ids = itertools.count(5900)
# "ENCA" prefix — see tests/test_intake_resolution.py's _ramq_numbers.
_ramq_numbers = itertools.count(1)
_texts = itertools.count(1)

CLEAN_RESULT = {"codes": [MOCK_RESULT["codes"][0]], "notes": None}  # one high-confidence code
NEEDS_CONFIRMATION_RESULT = {
    "codes": [MOCK_RESULT["codes"][0] | {"needs_confirmation": ["Confirmer la taille de la clientèle"]}],
    "notes": None,
}


@pytest.fixture
async def me():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


async def _seed_patient(full_name: str = "Roch Desjardins"):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            ramq_number=f"ENCA{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )


def _note_text(nam: str | None = None) -> str:
    """A fresh note each call: the same text twice would be a duplicate."""
    header = f"**NAM :** {nam}\n\n" if nam else ""
    return f"{header}Motif : suivi d'hypertension artérielle, visite {next(_texts)}."


def _model(billing=MOCK_RESULT, extractions: int = 1):
    """The chat model, answering `extractions` pipeline runs (summary, then codes)."""
    patcher = patch("app.extraction.engine.get_client")
    mock_get_client = patcher.start()
    mock_get_client.return_value.achat = AsyncMock(
        side_effect=[_mock_response(MOCK_SUMMARY_RESULT), _mock_response(billing)] * extractions
    )
    return patcher


def _paste(client: TestClient, text: str, *, billing=MOCK_RESULT, **fields):
    patcher = _model(billing)
    try:
        return client.post("/intake/notes", json={"text": text, **fields})
    finally:
        patcher.stop()


def _row(client: TestClient, encounter_id: int) -> dict:
    [row] = [row for row in client.get("/encounters").json() if row["id"] == encounter_id]
    return row


async def _encounter_count(user_id: int) -> int:
    async with session_scope() as session:
        return await session.scalar(select(func.count()).select_from(Encounter).where(Encounter.user_id == user_id))


# --- POST /intake/notes -------------------------------------------------------------------


async def test_push_a_note_with_a_known_nam_is_extracted_and_ready(me, client):
    patient = await _seed_patient()

    response = _paste(client, _note_text(patient.ramq_number), batch_label="Urgence nuit")

    assert response.status_code == 200
    [outcome] = response.json()
    assert outcome["outcome"] == "new"
    assert outcome["patient_id"] == patient.id
    assert outcome["enqueued"] is True
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "prêt"
    assert row["code_count"] == 2
    assert row["batch_label"] == "Urgence nuit"
    assert row["source_system"] == "manual"
    assert row["channel"] == "paste"
    # Masked in the list...
    assert row["patient"] == {
        "id": patient.id,
        "display_name": "Roch D.",
        "nam": f"{patient.ramq_number[:4]} ******{patient.ramq_number[-2:]}",
    }
    # ...in full in the detail, with the run in /extract's shape.
    detail = client.get(f"/encounters/{outcome['encounter_id']}").json()
    assert detail["patient"]["full_name"] == "Roch Desjardins"
    assert detail["patient"]["nam"] == patient.ramq_number
    assert detail["status"] == "prêt"
    assert detail["extraction"]["billing"]["task"] == "billing_codes"
    assert [c["code"] for c in detail["extraction"]["billing"]["result"]["codes"]] == [
        "TEST-BP-MGMT",
        "TEST-BLOODWORK-ORDER",
    ]
    async with session_scope() as session:
        run = await session.get(ExtractionRun, detail["extraction"]["extraction_run_id"])
    assert run.encounter_id == outcome["encounter_id"]
    assert run.patient_id == patient.id


async def test_push_an_er_shift_paste_receives_one_note_per_header(me, client):
    first, second = await _seed_patient(), await _seed_patient("Louise Tremblay")
    shift = f"{_note_text(first.ramq_number)}\n\n{_note_text(second.ramq_number)}"

    patcher = _model(extractions=2)
    try:
        response = client.post("/intake/notes", json={"text": shift, "batch_label": "Urgence nuit"})
    finally:
        patcher.stop()

    assert response.status_code == 200
    assert [o["patient_id"] for o in response.json()] == [first.id, second.id]


async def test_push_structured_source_notes(me, client):
    patient = await _seed_patient()
    note = {
        "source_system": "omnimed",
        "channel": "extension",
        "external_note_id": "N-1",
        "nam": patient.ramq_number,
        "service_date": "2026-03-04",
        "text": _note_text(),
    }

    patcher = _model()
    try:
        response = client.post("/intake/notes", json=[note])
    finally:
        patcher.stop()

    assert response.status_code == 200
    [outcome] = response.json()
    assert outcome["patient_id"] == patient.id
    # Dated by the source: listed on that day, not on the day it was received.
    listed = client.get("/encounters", params={"date": "2026-03-04"}).json()
    assert [row["id"] for row in listed] == [outcome["encounter_id"]]
    assert listed[0]["source_system"] == "omnimed"
    assert outcome["encounter_id"] not in [row["id"] for row in client.get("/encounters").json()]


async def test_push_with_an_unknown_nam_waits_for_a_patient_then_a_manual_pick_extracts_it(me, client):
    response = _paste(client, _note_text("ZZZZ99999999"))

    [outcome] = response.json()
    assert outcome["patient_id"] is None
    assert outcome["enqueued"] is False
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "à associer"
    assert row["patient"] is None
    assert row["code_count"] is None
    assert row["all_clean"] is False

    patient = await _seed_patient()
    patcher = _model()
    try:
        picked = client.post(f"/encounters/{outcome['encounter_id']}/patient", json={"patient_id": patient.id})
    finally:
        patcher.stop()

    assert picked.status_code == 200
    assert picked.json()["status"] == "prêt"
    assert picked.json()["patient"]["id"] == patient.id
    assert picked.json()["extraction"] is not None
    assert _row(client, outcome["encounter_id"])["status"] == "prêt"


async def test_a_duplicate_push_stores_no_new_row(me, client):
    patient = await _seed_patient()
    text = _note_text(patient.ramq_number)
    [first] = _paste(client, text).json()

    [again] = _paste(client, text).json()

    assert again["outcome"] == "duplicate"
    assert again["encounter_id"] == first["encounter_id"]
    assert again["enqueued"] is False
    assert await _encounter_count(me.id) == 1


async def test_push_rejects_an_empty_paste(me, client):
    response = client.post("/intake/notes", json={"text": "   \n  "})
    assert response.status_code == 422
    assert await _encounter_count(me.id) == 0


async def test_push_rejects_a_note_with_no_text_left_once_normalized(me, client):
    note = {"source_system": "omnimed", "channel": "extension", "text": "<script>x</script>"}
    response = client.post("/intake/notes", json=[note])
    assert response.status_code == 422


# --- POST /intake/upload ------------------------------------------------------------------


async def test_upload_a_text_file(me, client):
    patient = await _seed_patient()
    patcher = _model()
    try:
        response = client.post(
            "/intake/upload",
            files={"file": ("notes.txt", _note_text(patient.ramq_number).encode(), "text/plain")},
            data={"batch_label": "Clinique matin"},
        )
    finally:
        patcher.stop()

    assert response.status_code == 200
    [outcome] = response.json()
    assert outcome["patient_id"] == patient.id
    row = _row(client, outcome["encounter_id"])
    assert row["channel"] == "upload"
    assert row["batch_label"] == "Clinique matin"


async def test_upload_rejects_anything_but_text(me, client):
    response = client.post("/intake/upload", files={"file": ("notes.pdf", b"%PDF-1.7", "application/pdf")})
    assert response.status_code == 422
    assert await _encounter_count(me.id) == 0


# --- /encounters --------------------------------------------------------------------------


async def test_another_physicians_encounter_is_not_found(me, client):
    patient = await _seed_patient()
    [mine] = _paste(client, _note_text("ZZZZ99999999")).json()

    someone_else = physician(next(_physician_ids))
    await ensure_user_row(someone_else)
    app.dependency_overrides[get_current_user] = lambda: someone_else

    assert client.get(f"/encounters/{mine['encounter_id']}").status_code == 404
    assert client.post(f"/encounters/{mine['encounter_id']}/patient", json={"patient_id": patient.id}).status_code == 404
    assert client.post(f"/encounters/{mine['encounter_id']}/extract").status_code == 404
    assert client.get("/encounters").json() == []
    async with session_scope() as session:
        assert (await session.get(Encounter, mine["encounter_id"])).patient_id is None


@pytest.mark.parametrize(
    ("billing", "all_clean"),
    [
        (CLEAN_RESULT, True),
        (MOCK_RESULT, False),  # one medium-confidence code
        (NEEDS_CONFIRMATION_RESULT, False),
        ({"codes": [], "notes": None}, False),  # nothing to approve
    ],
)
async def test_all_clean(me, client, billing, all_clean):
    patient = await _seed_patient()
    [outcome] = _paste(client, _note_text(patient.ramq_number), billing=billing).json()
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "prêt"
    assert row["all_clean"] is all_clean


async def test_a_reviewed_encounter_is_never_all_clean(me, client):
    patient = await _seed_patient()
    [outcome] = _paste(client, _note_text(patient.ramq_number), billing=CLEAN_RESULT).json()
    run_id = client.get(f"/encounters/{outcome['encounter_id']}").json()["extraction"]["extraction_run_id"]

    claim = client.post(
        "/claims",
        json={"extraction_run_id": run_id, "service_date": "2026-03-04", "selected_codes": [{"code": "TEST-BP-MGMT"}]},
    )

    assert claim.status_code == 201
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "revu"
    assert row["all_clean"] is False


async def test_list_defaults_to_the_clinics_today(me, client):
    [outcome] = _paste(client, _note_text("ZZZZ99999999")).json()
    tomorrow = ClinicClock().today() + timedelta(days=1)

    app.dependency_overrides[get_clock] = lambda: type("Pinned", (), {"today": lambda self: tomorrow})()
    try:
        assert client.get("/encounters").json() == []
    finally:
        app.dependency_overrides.pop(get_clock)
    assert [row["id"] for row in client.get("/encounters").json()] == [outcome["encounter_id"]]


async def test_get_an_unknown_encounter_is_not_found(me, client):
    assert client.get("/encounters/999999").status_code == 404


async def test_pick_refuses_an_encounter_that_already_has_a_patient(me, client):
    patient = await _seed_patient()
    [outcome] = _paste(client, _note_text(patient.ramq_number)).json()
    other = await _seed_patient("Louise Tremblay")

    response = client.post(f"/encounters/{outcome['encounter_id']}/patient", json={"patient_id": other.id})

    assert response.status_code == 409


async def test_pick_refuses_an_unknown_patient(me, client):
    [outcome] = _paste(client, _note_text("ZZZZ99999999")).json()
    response = client.post(f"/encounters/{outcome['encounter_id']}/patient", json={"patient_id": 999999})
    assert response.status_code == 404
    assert _row(client, outcome["encounter_id"])["status"] == "à associer"


async def test_extract_on_demand_retries_a_failed_extraction(me, client):
    patient = await _seed_patient()
    patcher = patch("app.extraction.engine.get_client")
    mock_get_client = patcher.start()
    mock_get_client.return_value.achat = AsyncMock(side_effect=RuntimeError("modèle indisponible"))
    try:
        [outcome] = client.post("/intake/notes", json={"text": _note_text(patient.ramq_number)}).json()
    finally:
        patcher.stop()
    assert _row(client, outcome["encounter_id"])["status"] == "échec"

    patcher = _model(billing=CLEAN_RESULT)
    try:
        response = client.post(f"/encounters/{outcome['encounter_id']}/extract")
    finally:
        patcher.stop()

    assert response.status_code == 200
    assert [c["code"] for c in response.json()["billing"]["result"]["codes"]] == ["TEST-BP-MGMT"]
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "prêt"
    assert row["all_clean"] is True


async def test_extract_on_demand_refuses_an_encounter_without_a_patient(me, client):
    [outcome] = _paste(client, _note_text("ZZZZ99999999")).json()
    assert client.post(f"/encounters/{outcome['encounter_id']}/extract").status_code == 409


# --- masking ------------------------------------------------------------------------------


def test_mask_name_keeps_the_given_name_and_surname_initials():
    assert mask_name("Roch Desjardins") == "Roch D."
    assert mask_name("Marie-Ève Côté Lavoie") == "Marie-Ève C. L."
    assert mask_name("Cher") == "Cher"
    assert mask_name("") == ""


def test_mask_nam_hides_the_birth_date_digits():
    assert mask_nam("DESR81021001") == "DESR ******01"
    assert mask_nam(None) is None
