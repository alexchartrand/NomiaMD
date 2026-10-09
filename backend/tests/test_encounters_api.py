"""The intake and inbox routes over HTTP (step 09): pushing notes in (/intake/notes,
/intake/upload) and working the inbox (/encounters...). The billing pipeline runs for real
against the mocked model (two chat calls per extraction) and conftest's stub retriever.

Each test acts as its own physician, so the inbox only ever holds that test's encounters.
Seeds through session_scope (committed): the routes open their own sessions."""

import itertools
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import get_current_user
from app.clock import ClinicClock
from app.encounters.masking import mask_name, mask_nam
from app.encounters.readiness import is_all_clean
from app.intake import EncounterStatus
from app.main import app
from app.postgresdb import Encounter, ExtractionRun, Gender, PatientRepository, session_scope
from tests.db_helpers import ensure_user_row, physician
from tests.test_extraction import MOCK_RESULT, MOCK_SUMMARY_RESULT, _mock_response

_physician_ids = itertools.count(5900)
# "ENCA" prefix — see tests/test_intake_resolution.py's _ramq_numbers.
_ramq_numbers = itertools.count(1)
_texts = itertools.count(1)

CLEAN_RESULT = {"codes": [MOCK_RESULT["codes"][0]], "notes": None}  # one high-confidence code
# The model is sure of a code, but only with medium confidence.
UNSURE_RETAINED_RESULT = {"codes": [MOCK_RESULT["other_possible_codes"][0]], "notes": None}
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


async def _seed_patient(full_name: str = "Roch Desjardins", **fields):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            ramq_number=f"ENCA{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=fields.pop("is_vulnerable", False),
            **fields,
        )


def _note_text(nam: str | None = None) -> str:
    """A fresh note each call: the same text twice would be a duplicate."""
    header = f"**NAM :** {nam}\n\n" if nam else ""
    return f"{header}Motif : suivi d'hypertension artérielle, visite {next(_texts)}."


def _model(billing=MOCK_RESULT, extractions: int = 1):
    """The chat model, answering `extractions` pipeline runs (summary, then codes)."""
    patcher = patch("app.extraction.engine.get_client")
    mock_get_client = patcher.start()
    mock_get_client.return_value.chat = AsyncMock(
        side_effect=[_mock_response(MOCK_SUMMARY_RESULT), _mock_response(billing)] * extractions
    )
    return patcher


def _paste(client: TestClient, text: str, *, billing=MOCK_RESULT, **fields):
    patcher = _model(billing)
    try:
        return client.post("/intake/notes", json={"text": text, **fields})
    finally:
        patcher.stop()


def _push(client: TestClient, patient, *, billing=MOCK_RESULT, service_date: date | None = None, **meta):
    """One structured note, dated (today by default) — what the extension or a scribe
    sends, unlike a paste whose date only the extraction can find."""
    note = {
        "source_system": meta.pop("source_system", "omnimed"),
        "channel": meta.pop("channel", "extension"),
        "nam": patient.ramq_number,
        "service_date": (service_date or ClinicClock().today()).isoformat(),
        "meta": meta,
        "text": _note_text(),
    }
    patcher = _model(billing)
    try:
        response = client.post("/intake/notes", json=[note])
    finally:
        patcher.stop()
    assert response.status_code == 200
    [outcome] = response.json()
    return outcome["encounter_id"]


def _row(client: TestClient, encounter_id: int) -> dict:
    [row] = [row for row in client.get("/encounters").json() if row["id"] == encounter_id]
    return row


def _listed_ids(client: TestClient) -> list[int]:
    return [row["id"] for row in client.get("/encounters").json()]


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
    # The high-confidence code only (what the review starts with ticked), at its fee.
    assert row["codes"] == ["TEST-BP-MGMT"]
    assert row["indicative_total"] == 33.15
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
    # The patient's billing facts, registration unknown without practice numbers.
    assert detail["patient"]["date_of_birth"] == "1981-02-10"
    assert detail["patient"]["is_vulnerable"] is False
    assert detail["patient"]["is_registered"] is None
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
    listed = client.get("/encounters", params={"date_from": "2026-03-04", "date_to": "2026-03-04"}).json()
    assert [row["id"] for row in listed] == [outcome["encounter_id"]]
    assert listed[0]["source_system"] == "omnimed"
    today = ClinicClock().today().isoformat()
    assert client.get("/encounters", params={"date_from": today, "date_to": today}).json() == []


async def test_the_detail_derives_registration_against_the_viewing_physician(me, client):
    me.practice_number = "12345"
    mine = await _seed_patient(family_doctor_practice_number="12345", is_vulnerable=True)
    theirs = await _seed_patient("Marie Tremblay", family_doctor_practice_number="99999")

    def patient_of(patient):
        encounter_id = _push(client, patient)
        return client.get(f"/encounters/{encounter_id}").json()["patient"]

    assert patient_of(mine)["is_registered"] is True
    assert patient_of(mine)["is_vulnerable"] is True
    assert patient_of(theirs)["is_registered"] is False


async def test_push_with_an_unknown_nam_waits_for_a_patient_then_a_manual_pick_extracts_it(me, client):
    response = _paste(client, _note_text("ZZZZ99999999"))

    [outcome] = response.json()
    assert outcome["patient_id"] is None
    assert outcome["enqueued"] is False
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "à associer"
    assert row["patient"] is None
    assert row["code_count"] is None
    assert row["codes"] is None
    assert row["indicative_total"] is None
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


async def test_paste_stores_the_care_setting_the_physician_picked(me, client):
    [outcome] = _paste(client, _note_text("ZZZZ99999999"), care_setting="urgence").json()

    async with session_scope() as session:
        encounter = await session.get(Encounter, outcome["encounter_id"])
    assert encounter.encounter_meta == {"care_setting": "urgence"}


def test_paste_rejects_an_unknown_care_setting(me, client):
    response = client.post("/intake/notes", json={"text": _note_text("ZZZZ99999999"), "care_setting": "bureau"})
    assert response.status_code == 422


# --- POST /intake/upload ------------------------------------------------------------------


async def test_upload_a_text_file(me, client):
    patient = await _seed_patient()
    patcher = _model()
    try:
        response = client.post(
            "/intake/upload",
            files={"file": ("notes.txt", _note_text(patient.ramq_number).encode(), "text/plain")},
            data={"batch_label": "Clinique matin", "care_setting": "cabinet"},
        )
    finally:
        patcher.stop()

    assert response.status_code == 200
    [outcome] = response.json()
    assert outcome["patient_id"] == patient.id
    row = _row(client, outcome["encounter_id"])
    assert row["channel"] == "upload"
    assert row["batch_label"] == "Clinique matin"
    async with session_scope() as session:
        encounter = await session.get(Encounter, outcome["encounter_id"])
    assert encounter.encounter_meta["care_setting"] == "cabinet"


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
        (MOCK_RESULT, True),  # its medium-confidence code is only a possible one
        (UNSURE_RETAINED_RESULT, False),
        (NEEDS_CONFIRMATION_RESULT, False),
        ({"codes": [], "notes": None}, False),  # nothing to approve
    ],
)
async def test_all_clean(me, client, billing, all_clean):
    patient = await _seed_patient()
    encounter_id = _push(client, patient, billing=billing)
    row = _row(client, encounter_id)
    assert row["status"] == "prêt"
    assert row["all_clean"] is all_clean
    assert row["extraction_run_id"] is not None


async def test_an_undated_encounter_is_never_all_clean(me, client):
    """A claim needs its date: a paste the extraction couldn't date gets opened."""
    patient = await _seed_patient()
    [outcome] = _paste(client, _note_text(patient.ramq_number), billing=CLEAN_RESULT).json()
    row = _row(client, outcome["encounter_id"])
    assert row["status"] == "prêt"
    assert row["service_date"] is None
    assert row["all_clean"] is False


async def test_a_reviewed_encounter_is_never_all_clean(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient, billing=CLEAN_RESULT)
    run_id = _row(client, encounter_id)["extraction_run_id"]

    claim = client.post(
        "/claims",
        json={"extraction_run_id": run_id, "service_date": "2026-03-04", "selected_codes": [{"code": "TEST-BP-MGMT"}]},
    )

    assert claim.status_code == 201
    row = _row(client, encounter_id)
    assert row["status"] == "revu"
    assert row["all_clean"] is False


async def test_a_reviewed_encounter_shows_the_codes_billed_not_the_codes_proposed(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient)  # proposes two codes
    run_id = _row(client, encounter_id)["extraction_run_id"]
    assert _row(client, encounter_id)["codes"] == ["TEST-BP-MGMT"]

    # The physician bills the medium-confidence code instead, which has no fee in the table.
    claim = client.post(
        "/claims",
        json={
            "extraction_run_id": run_id,
            "service_date": "2026-03-04",
            "selected_codes": [{"code": "TEST-BLOODWORK-ORDER"}],
        },
    )

    assert claim.status_code == 201
    row = _row(client, encounter_id)
    assert row["code_count"] == 1
    assert row["codes"] == ["TEST-BLOODWORK-ORDER"]
    assert row["indicative_total"] is None
    detail = client.get(f"/encounters/{encounter_id}").json()
    assert [c["code"] for c in detail["claim"]["codes"]] == ["TEST-BLOODWORK-ORDER"]
    assert len(detail["extraction"]["billing"]["result"]["codes"]) == 2


async def test_an_encounter_without_a_claim_has_none(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient)

    assert client.get(f"/encounters/{encounter_id}").json()["claim"] is None


async def test_list_a_range_of_days(me, client):
    """A physician who bills at the end of the week reads several days at once."""
    patient = await _seed_patient()
    monday = _push(client, patient, service_date=date(2026, 3, 2))
    wednesday = _push(client, patient, service_date=date(2026, 3, 4))
    next_monday = _push(client, patient, service_date=date(2026, 3, 9))
    undated_today = _paste(client, _note_text("ZZZZ99999999")).json()[0]["encounter_id"]

    def listed(**params) -> list[int]:
        response = client.get("/encounters", params=params)
        assert response.status_code == 200
        return [row["id"] for row in response.json()]

    assert listed(date_from="2026-03-02", date_to="2026-03-06") == [monday, wednesday]
    assert listed(date_from="2026-03-04") == [wednesday, next_monday, undated_today]
    assert listed(date_to="2026-03-04") == [monday, wednesday]
    # No bounds at all: everything, the undated one on the day it was received.
    assert listed() == [monday, wednesday, next_monday, undated_today]
    today = ClinicClock().today().isoformat()
    assert listed(date_from=today, date_to=today) == [undated_today]


async def test_list_refuses_a_range_that_ends_before_it_starts(me, client):
    response = client.get("/encounters", params={"date_from": "2026-03-06", "date_to": "2026-03-02"})
    assert response.status_code == 422


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
    mock_get_client.return_value.chat = AsyncMock(side_effect=RuntimeError("modèle indisponible"))
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
    assert row["codes"] == ["TEST-BP-MGMT"]


async def test_extract_on_demand_refuses_an_encounter_without_a_patient(me, client):
    [outcome] = _paste(client, _note_text("ZZZZ99999999")).json()
    assert client.post(f"/encounters/{outcome['encounter_id']}/extract").status_code == 409


# --- doublon possible --------------------------------------------------------------------


async def _same_visit_twice(client: TestClient, billing=CLEAN_RESULT) -> tuple[int, int]:
    """The extension's capture and the scribe's note of one 09:00 visit."""
    patient = await _seed_patient()
    capture = _push(client, patient, billing=billing, time_start="09:00:00")
    scribe = _push(client, patient, billing=billing, source_system="plume", channel="scribe_webhook", time_start="09:10:00")
    return capture, scribe


async def test_two_visits_hours_apart_are_not_flagged(me, client):
    patient = await _seed_patient()
    morning = _push(client, patient, billing=CLEAN_RESULT, time_start="09:00:00")
    afternoon = _push(client, patient, billing=CLEAN_RESULT, time_start="15:00:00")

    for encounter_id in (morning, afternoon):
        row = _row(client, encounter_id)
        assert row["possible_duplicate_ids"] == []
        assert row["all_clean"] is True


async def test_a_capture_and_a_scribe_note_of_one_visit_are_flagged_and_not_approvable(me, client):
    capture, scribe = await _same_visit_twice(client)

    assert _row(client, capture)["possible_duplicate_ids"] == [scribe]
    assert _row(client, scribe)["possible_duplicate_ids"] == [capture]
    # Approve-all skips them until the physician answers.
    assert _row(client, capture)["all_clean"] is False
    assert _row(client, scribe)["all_clean"] is False


async def test_confirming_hides_one_and_it_is_never_billed(me, client):
    capture, scribe = await _same_visit_twice(client)
    hidden_run = _row(client, capture)["extraction_run_id"]

    response = client.post(f"/encounters/{capture}/duplicate-of/{scribe}")

    assert response.status_code == 204
    assert _listed_ids(client) == [scribe]
    kept = _row(client, scribe)
    assert kept["possible_duplicate_ids"] == []
    assert kept["all_clean"] is True
    assert client.get(f"/encounters/{capture}").json()["duplicate_of_id"] == scribe
    claim = client.post(
        "/claims",
        json={
            "extraction_run_id": hidden_run,
            "service_date": kept["service_date"],
            "selected_codes": [{"code": "TEST-BP-MGMT"}],
        },
    )
    assert claim.status_code == 409


async def test_dismissing_clears_the_flag_for_good(me, client):
    capture, scribe = await _same_visit_twice(client)

    response = client.post(f"/encounters/{scribe}/not-duplicate")

    assert response.status_code == 204
    for encounter_id in (capture, scribe):
        row = _row(client, encounter_id)
        assert row["possible_duplicate_ids"] == []
        assert row["all_clean"] is True
    assert sorted(_listed_ids(client)) == sorted([capture, scribe])


async def test_confirming_refuses_to_hide_a_billed_encounter(me, client):
    capture, scribe = await _same_visit_twice(client)
    row = _row(client, capture)
    claim = client.post(
        "/claims",
        json={
            "extraction_run_id": row["extraction_run_id"],
            "service_date": row["service_date"],
            "selected_codes": [{"code": "TEST-BP-MGMT"}],
        },
    )
    assert claim.status_code == 201

    assert client.post(f"/encounters/{capture}/duplicate-of/{scribe}").status_code == 409
    # Keeping the billed one instead is fine.
    assert client.post(f"/encounters/{scribe}/duplicate-of/{capture}").status_code == 204
    assert _listed_ids(client) == [capture]


async def test_confirming_refuses_itself_and_a_hidden_keeper(me, client):
    capture, scribe = await _same_visit_twice(client)
    assert client.post(f"/encounters/{capture}/duplicate-of/{capture}").status_code == 422

    assert client.post(f"/encounters/{capture}/duplicate-of/{scribe}").status_code == 204
    assert client.post(f"/encounters/{scribe}/duplicate-of/{capture}").status_code == 409


async def test_duplicate_answers_are_scoped_to_the_physician(me, client):
    capture, scribe = await _same_visit_twice(client)

    someone_else = physician(next(_physician_ids))
    await ensure_user_row(someone_else)
    app.dependency_overrides[get_current_user] = lambda: someone_else

    assert client.post(f"/encounters/{capture}/duplicate-of/{scribe}").status_code == 404
    assert client.post(f"/encounters/{capture}/not-duplicate").status_code == 404

    app.dependency_overrides[get_current_user] = lambda: me
    assert _row(client, capture)["possible_duplicate_ids"] == [scribe]


async def test_delete_an_encounter(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient)

    assert _row(client, encounter_id)["deletable"] is True
    assert client.delete(f"/encounters/{encounter_id}").status_code == 204

    assert client.get(f"/encounters/{encounter_id}").status_code == 404
    assert await _encounter_count(me.id) == 0


async def test_an_encounter_with_a_claim_cannot_be_deleted(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient)
    run_id = _row(client, encounter_id)["extraction_run_id"]
    client.post(
        "/claims",
        json={"extraction_run_id": run_id, "service_date": "2026-03-04", "selected_codes": [{"code": "TEST-BP-MGMT"}]},
    )

    assert _row(client, encounter_id)["deletable"] is False
    assert client.delete(f"/encounters/{encounter_id}").status_code == 409
    assert client.get(f"/encounters/{encounter_id}").status_code == 200


async def test_deleting_is_scoped_to_the_physician(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient)

    someone_else = physician(next(_physician_ids))
    await ensure_user_row(someone_else)
    app.dependency_overrides[get_current_user] = lambda: someone_else

    assert client.delete(f"/encounters/{encounter_id}").status_code == 404
    app.dependency_overrides[get_current_user] = lambda: me
    assert client.get(f"/encounters/{encounter_id}").status_code == 200


# --- masking ------------------------------------------------------------------------------


def test_mask_name_keeps_the_given_name_and_surname_initials():
    assert mask_name("Roch Desjardins") == "Roch D."
    assert mask_name("Marie-Ève Côté Lavoie") == "Marie-Ève C. L."
    assert mask_name("Cher") == "Cher"
    assert mask_name("") == ""


def test_mask_nam_hides_the_birth_date_digits():
    assert mask_nam("DESR81021001") == "DESR ******01"
    assert mask_nam(None) is None


# --- readiness ----------------------------------------------------------------------------


def _extraction(*codes):
    """Just what is_all_clean reads: the latest run's codes."""
    return SimpleNamespace(billing=SimpleNamespace(result=SimpleNamespace(codes=list(codes))))


def _code(fees: int = 1, confidence: str = "high", needs_confirmation=(), retained: bool = True):
    return SimpleNamespace(
        confidence=confidence, needs_confirmation=list(needs_confirmation), fees=[object()] * fees, retained=retained
    )


def test_a_code_with_several_fees_is_not_clean():
    """Approve-all would bill the first fee: the physician picks one in the review."""
    ready = {"service_date": date(2026, 3, 4), "possible_duplicate": False}
    assert is_all_clean(EncounterStatus.PRET, _extraction(_code(fees=1), _code(fees=0)), **ready)
    assert not is_all_clean(EncounterStatus.PRET, _extraction(_code(fees=1), _code(fees=2)), **ready)


def test_only_the_retained_codes_decide_cleanliness():
    """Approving bills the retained codes: an unsure possible code doesn't block it, and
    possible codes alone leave nothing to approve."""
    ready = {"service_date": date(2026, 3, 4), "possible_duplicate": False}
    possible = _code(confidence="low", needs_confirmation=["?"], fees=3, retained=False)
    assert is_all_clean(EncounterStatus.PRET, _extraction(_code(), possible), **ready)
    assert not is_all_clean(EncounterStatus.PRET, _extraction(possible), **ready)
