"""GET /dashboard end-to-end: notes pushed through intake (mocked model, stub retriever),
claims saved and billed through their own routes, then the summary read back.

Each test acts as its own physician, so the dashboard only ever holds that test's data.
"Today" is pinned to the clinic's real today through get_clock: received_at and a bill's
generated_at are stamped by the real DB clock, so a far-off pinned date would split them
from the service dates under test."""

import itertools
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.clock import ClinicClock, get_clock
from app.dashboard.activity import week_start
from app.main import app
from app.postgresdb import ExtractionStageInput, Gender, PatientRepository, session_scope
from tests.db_helpers import ensure_user_row, physician, seed_run
from tests.test_encounters_api import CLEAN_RESULT, _model, _note_text, _paste, _push

_physician_ids = itertools.count(7000)
# "DASH" prefix: patients are globally unique by NAM across the shared test DB.
_ramq_numbers = itertools.count(1)

TODAY = ClinicClock().today()


class _FixedClock:
    def __init__(self, today: date) -> None:
        self._today = today

    def today(self) -> date:
        return self._today


@pytest.fixture
async def me():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def client():
    app.dependency_overrides[get_clock] = lambda: _FixedClock(TODAY)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_clock, None)


async def _seed_patient(full_name: str = "Roch Desjardins"):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            ramq_number=f"DASH{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )


def _billing(fee_amount: float) -> dict:
    code = CLEAN_RESULT["codes"][0]
    return {
        "codes": [code | {"fees": [{"amount": fee_amount, "amount_text": None, "context": None, "lieux": [], "majoration": None}]}],
        "notes": None,
    }


async def _draft_claim(client: TestClient, user_id: int, patient, *, service_date: date, fee_amount: float = 33.15) -> dict:
    """A saved claim not on a bill yet. Its run's encounter is undated, so it counts on
    today and shows as "revu"."""
    async with session_scope() as session:
        run = await seed_run(
            session,
            user_id=user_id,
            patient_id=patient.id,
            note_text=_note_text(),
            stages=[ExtractionStageInput(task="billing_codes", model="test", result=_billing(fee_amount))],
        )
    response = client.post(
        "/claims",
        json={
            "extraction_run_id": run.id,
            "service_date": service_date.isoformat(),
            "selected_codes": [{"code": CLEAN_RESULT["codes"][0]["code"], "fee_index": 0}],
        },
        params={"confirm_duplicate": "true"},
    )
    assert response.status_code == 201
    return response.json()


def _dashboard(client: TestClient) -> dict:
    response = client.get("/dashboard")
    assert response.status_code == 200
    return response.json()


async def test_an_empty_dashboard(me, client):
    dashboard = _dashboard(client)

    assert dashboard["today"] == TODAY.isoformat()
    assert set(dashboard["tasks"].values()) == {0}
    assert dashboard["kpis"] == {
        "encounters_this_week": 0,
        "draft_count": 0,
        "draft_total": 0.0,
        "billed_this_month": 0.0,
    }
    assert dashboard["deadlines"] == []
    assert dashboard["recent_encounters"] == []
    assert len(dashboard["weekly_activity"]) == 8
    assert dashboard["weekly_activity"][-1]["week_start"] == week_start(TODAY).isoformat()


async def test_tasks_count_what_is_left_to_do(me, client):
    patient = await _seed_patient()
    clean = _push(client, patient, billing=CLEAN_RESULT)
    # A medium-confidence code: not approvable. Another day, or it's a possible duplicate.
    to_review = _push(client, patient, service_date=TODAY - timedelta(days=1))
    [unmatched] = _paste(client, _note_text("ZZZZ99999999")).json()
    with patch("app.extraction.engine.get_client") as get_client:
        get_client.return_value.achat = AsyncMock(side_effect=RuntimeError("modèle indisponible"))
        [failed] = client.post("/intake/notes", json={"text": _note_text(patient.ramq_number)}).json()

    tasks = _dashboard(client)["tasks"]

    assert tasks == {
        "to_do": 4,
        "to_review": 2,
        "approvable": 1,
        "to_associate": 1,
        "failed": 1,
        "extracting": 0,
        "possible_duplicates": 0,
    }
    recent = [row["id"] for row in _dashboard(client)["recent_encounters"]]
    assert recent == [failed["encounter_id"], unmatched["encounter_id"], to_review, clean]


async def test_an_old_visit_received_twice_is_still_a_possible_duplicate(me, client):
    patient = await _seed_patient()
    long_ago = TODAY - timedelta(days=200)
    _push(client, patient, service_date=long_ago, time_start="09:00:00")
    _push(client, patient, service_date=long_ago, time_start="09:10:00", source_system="plume", channel="scribe_webhook")

    assert _dashboard(client)["tasks"]["possible_duplicates"] == 2


async def test_recent_encounters_are_the_last_six_received(me, client):
    patient = await _seed_patient()
    ids = [_push(client, patient, service_date=TODAY - timedelta(days=n)) for n in range(8)]

    recent = [row["id"] for row in _dashboard(client)["recent_encounters"]]

    assert recent == list(reversed(ids))[:6]


async def test_deadlines_list_what_can_still_be_billed_first_then_what_is_overdue(me, client):
    patient = await _seed_patient()
    long_overdue = _push(client, patient, service_date=TODAY - timedelta(days=200))
    overdue = _push(client, patient, service_date=TODAY - timedelta(days=95))
    soon = _push(client, patient, service_date=TODAY - timedelta(days=80))
    _push(client, patient, service_date=TODAY - timedelta(days=60))  # a month left: not yet
    draft = await _draft_claim(client, me.id, patient, service_date=TODAY - timedelta(days=85))

    deadlines = _dashboard(client)["deadlines"]

    assert [(d["kind"], d["id"], d["days_left"]) for d in deadlines] == [
        ("claim", draft["id"], 5),
        ("encounter", soon, 10),
        ("encounter", overdue, -5),
        ("encounter", long_overdue, -110),
    ]
    assert deadlines[0]["patient_display"] == "Roch D."


async def test_a_reviewed_encounter_is_not_a_deadline_its_claim_is(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient, billing=CLEAN_RESULT, service_date=TODAY - timedelta(days=88))
    run_id = next(r for r in client.get("/encounters").json() if r["id"] == encounter_id)["extraction_run_id"]
    claim = client.post(
        "/claims",
        json={
            "extraction_run_id": run_id,
            "service_date": (TODAY - timedelta(days=88)).isoformat(),
            "selected_codes": [{"code": CLEAN_RESULT["codes"][0]["code"]}],
        },
    ).json()

    deadlines = _dashboard(client)["deadlines"]

    assert [(d["kind"], d["id"]) for d in deadlines] == [("claim", claim["id"])]


async def test_billing_figures(me, client):
    patient = await _seed_patient()
    billed = await _draft_claim(client, me.id, patient, service_date=TODAY, fee_amount=33.15)
    await _draft_claim(client, me.id, patient, service_date=TODAY, fee_amount=10.00)
    assert _dashboard(client)["kpis"] | {"encounters_this_week": None} == {
        "encounters_this_week": None,
        "draft_count": 2,
        "draft_total": 43.15,
        "billed_this_month": 0.0,
    }

    bill = client.post(
        "/bills",
        json={"start_date": TODAY.isoformat(), "end_date": TODAY.isoformat(), "claim_ids": [billed["id"]]},
    )
    assert bill.status_code == 201

    kpis = _dashboard(client)["kpis"]
    assert (kpis["draft_count"], kpis["draft_total"], kpis["billed_this_month"]) == (1, 10.00, 33.15)


async def test_weekly_activity_counts_received_and_reviewed(me, client):
    patient = await _seed_patient()
    _push(client, patient, service_date=TODAY)
    _push(client, patient, service_date=TODAY - timedelta(days=7))
    await _draft_claim(client, me.id, patient, service_date=TODAY)  # its encounter: today, revu

    dashboard = _dashboard(client)

    *_, last_week, this_week = dashboard["weekly_activity"]
    assert (this_week["received"], this_week["reviewed"]) == (2, 1)
    assert (last_week["received"], last_week["reviewed"]) == (1, 0)
    assert dashboard["kpis"]["encounters_this_week"] == 2


async def test_today_comes_from_the_clinic_clock(me, client):
    app.dependency_overrides[get_clock] = lambda: _FixedClock(date(2026, 3, 4))

    dashboard = _dashboard(client)

    assert dashboard["today"] == "2026-03-04"
    assert dashboard["weekly_activity"][-1]["week_start"] == "2026-03-02"


async def test_another_physicians_work_is_not_shown(me, client):
    patient = await _seed_patient()
    _push(client, patient, service_date=TODAY - timedelta(days=85))
    await _draft_claim(client, me.id, patient, service_date=TODAY)

    someone_else = physician(next(_physician_ids))
    await ensure_user_row(someone_else)
    app.dependency_overrides[get_current_user] = lambda: someone_else
    dashboard = _dashboard(client)

    assert set(dashboard["tasks"].values()) == {0}
    assert dashboard["kpis"]["draft_count"] == 0
    assert dashboard["deadlines"] == []
    assert dashboard["recent_encounters"] == []
