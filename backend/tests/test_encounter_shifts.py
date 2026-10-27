"""Encounter ↔ shift linking: ShiftMatcher's derived match, the care setting's resolution order
(picked shift → matched shift → the source's or paste's care setting), what a run records of
it, and the physician's pick over HTTP (PUT /encounters/{id}/shift, paste/upload `shift_id`)."""

import itertools
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import get_current_user
from app.main import app
from app.postgresdb import Encounter, ExtractionRun, Gender, PatientRepository, Shift, session_scope
from app.shifts import EncounterSetting, RunSettingSnapshot, ShiftMatcher, ShiftMatchOutcome
from tests.db_helpers import ensure_user_row, physician
from tests.test_encounters_api import CLEAN_RESULT, _model, _note_text, _paste, _push, _row

# Own physicians and NAMs ("ENSH"): test_encounters_api's counters aren't shared with this module.
_physician_ids = itertools.count(6900)
_ramq_numbers = itertools.count(1)

TUESDAY = date(2026, 10, 27)


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


async def _seed_patient():
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name="Roch Desjardins",
            ramq_number=f"ENSH{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )


def _shift(id: int, day: date, start: time, end: time, care_setting: str = "urgence", period: str = "soir") -> Shift:
    return Shift(
        id=id,
        user_id=1,
        work_site_id=1,
        care_setting=care_setting,
        period=period,
        service_date=day,
        start_time=start,
        end_time=end,
    )


# --- ShiftMatcher ---------------------------------------------------------------------------

DAY = _shift(1, TUESDAY, time(8), time(16), period="jour")
EVENING = _shift(2, TUESDAY, time(16), time(0))
MONDAY_NIGHT = _shift(3, date(2026, 10, 26), time(23), time(7), period="nuit")


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (time(9, 30), DAY),
        # The start is in, the end is out: 16:00 is the evening's.
        (time(16), EVENING),
        (time(23, 59), EVENING),
        # Monday's night reaches into Tuesday.
        (time(2), MONDAY_NIGHT),
    ],
)
def test_a_start_time_matches_the_shift_containing_it(start, expected):
    match = ShiftMatcher().match(TUESDAY, start, [MONDAY_NIGHT, DAY, EVENING])
    assert match.outcome is ShiftMatchOutcome.MATCHED
    assert match.shift is expected


def test_a_start_time_outside_every_shift_matches_none():
    match = ShiftMatcher().match(TUESDAY, time(7, 30), [DAY, EVENING])
    assert match.outcome is ShiftMatchOutcome.NONE
    assert match.shift is None


def test_without_a_time_every_shift_on_the_day_is_a_candidate():
    match = ShiftMatcher().match(TUESDAY, None, [MONDAY_NIGHT, DAY, EVENING])
    assert match.outcome is ShiftMatchOutcome.AMBIGUOUS
    assert match.candidates == [MONDAY_NIGHT, DAY, EVENING]
    assert match.shift is None


def test_without_a_time_a_lone_shift_on_the_day_matches():
    assert ShiftMatcher().match(TUESDAY, None, [EVENING]).shift is EVENING


def test_an_evening_ending_at_midnight_does_not_reach_the_next_day():
    monday_evening = _shift(4, date(2026, 10, 26), time(16), time(0))
    assert ShiftMatcher().match(TUESDAY, None, [monday_evening]).outcome is ShiftMatchOutcome.NONE


def test_an_undated_encounter_matches_nothing():
    assert ShiftMatcher().match(None, time(9), [DAY]).outcome is ShiftMatchOutcome.NONE


def test_the_run_snapshot_takes_the_encounters_own_day_type():
    snapshot = RunSettingSnapshot().of(EncounterSetting(care_setting=None, shift=MONDAY_NIGHT), TUESDAY)
    assert snapshot.shift_id == 3
    assert snapshot.shift_period == "nuit"
    assert snapshot.day_type == "semaine"
    # No date of its own: its shift's.
    saturday_shift = _shift(5, date(2026, 10, 31), time(8), time(16))
    assert RunSettingSnapshot().of(EncounterSetting(None, saturday_shift), None).day_type == "fin_de_semaine"


# --- Over HTTP ------------------------------------------------------------------------------


def _site(client, care_setting: str = "urgence", name: str | None = None) -> int:
    response = client.post("/work-sites", json={"name": name or f"Site {care_setting}", "care_setting": care_setting})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _schedule(client, site_id: int, start: str, end: str, period: str = "soir", day: date = TUESDAY) -> int:
    response = client.post(
        "/shifts",
        json={
            "work_site_id": site_id,
            "period": period,
            "service_date": day.isoformat(),
            "start_time": start,
            "end_time": end,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _latest_run(encounter_id: int) -> ExtractionRun:
    async with session_scope() as session:
        return await session.scalar(
            select(ExtractionRun).where(ExtractionRun.encounter_id == encounter_id).order_by(ExtractionRun.id.desc())
        )


async def test_a_note_in_a_shift_is_matched_and_extracted_under_its_care_setting(me, client):
    shift_id = _schedule(client, _site(client, "urgence"), "16:00", "00:00")
    patient = await _seed_patient()
    # The paste's own setting loses to the shift's.
    encounter_id = _push(client, patient, service_date=TUESDAY, time_start="18:30", care_setting="chsld")

    setting = _row(client, encounter_id)["setting"]
    assert setting["care_setting"] == "urgence"
    assert setting["shift"]["id"] == shift_id
    assert setting["shift"]["work_site_name"] == "Site urgence"
    assert setting["shift_picked"] is False
    assert setting["needs_shift_choice"] is False
    assert setting["differs_from_run"] is False

    run = await _latest_run(encounter_id)
    assert (run.care_setting, run.shift_id, run.shift_period, run.day_type) == ("urgence", shift_id, "soir", "semaine")
    detail = client.get(f"/encounters/{encounter_id}").json()
    assert detail["extraction"]["setting"] == {
        "care_setting": "urgence",
        "shift_id": shift_id,
        "shift_period": "soir",
        "day_type": "semaine",
    }


async def test_the_matched_shifts_care_setting_reaches_the_pipeline(me, client, monkeypatch):
    _schedule(client, _site(client, "chsld"), "08:00", "16:00", period="jour")
    seen = {}
    from app.extraction.pipeline import BillingPipeline

    original = BillingPipeline.run

    async def spy(self, transcript, **kwargs):
        seen["care_setting"] = kwargs.get("care_setting")
        return await original(self, transcript, **kwargs)

    monkeypatch.setattr(BillingPipeline, "run", spy)
    patient = await _seed_patient()
    _push(client, patient, service_date=TUESDAY, time_start="10:00")
    assert seen["care_setting"] == "chsld"


async def test_several_shifts_on_the_day_wait_for_the_physician(me, client):
    site_id = _site(client)
    day_id = _schedule(client, site_id, "08:00", "16:00", period="jour")
    evening_id = _schedule(client, site_id, "16:00", "00:00")
    patient = await _seed_patient()
    # No time: both fit. The paste's own setting stands meanwhile.
    encounter_id = _push(client, patient, billing=CLEAN_RESULT, service_date=TUESDAY, care_setting="gmf")

    row = _row(client, encounter_id)
    assert row["setting"]["needs_shift_choice"] is True
    assert row["setting"]["shift"] is None
    assert row["setting"]["care_setting"] == "gmf"
    assert [s["id"] for s in row["setting"]["shift_options"]] == [day_id, evening_id]
    assert row["all_clean"] is False


async def test_picking_a_shift_flags_the_run_until_it_is_re_extracted(me, client):
    site_id = _site(client)
    day_id = _schedule(client, site_id, "08:00", "16:00", period="jour")
    _schedule(client, site_id, "16:00", "00:00")
    patient = await _seed_patient()
    encounter_id = _push(client, patient, billing=CLEAN_RESULT, service_date=TUESDAY)

    response = client.put(f"/encounters/{encounter_id}/shift", json={"shift_id": day_id})
    assert response.status_code == 200, response.text
    setting = response.json()["setting"]
    assert setting["shift"]["id"] == day_id
    assert setting["shift_picked"] is True
    assert setting["needs_shift_choice"] is False
    assert setting["differs_from_run"] is True
    assert _row(client, encounter_id)["all_clean"] is False

    patcher = _model(CLEAN_RESULT)
    try:
        assert client.post(f"/encounters/{encounter_id}/extract").status_code == 200
    finally:
        patcher.stop()
    row = _row(client, encounter_id)
    assert row["setting"]["differs_from_run"] is False
    assert row["all_clean"] is True


async def test_withdrawing_the_pick_derives_the_shift_again(me, client):
    site_id = _site(client)
    evening_id = _schedule(client, site_id, "16:00", "00:00")
    other_id = _schedule(client, _site(client, "chsld"), "08:00", "16:00", period="jour")
    patient = await _seed_patient()
    encounter_id = _push(client, patient, service_date=TUESDAY, time_start="20:00")

    assert client.put(f"/encounters/{encounter_id}/shift", json={"shift_id": other_id}).json()["setting"][
        "care_setting"
    ] == "chsld"
    setting = client.put(f"/encounters/{encounter_id}/shift", json={"shift_id": None}).json()["setting"]
    assert setting["shift"]["id"] == evening_id
    assert setting["shift_picked"] is False


async def test_a_voided_picked_shift_no_longer_counts(me, client):
    site_id = _site(client)
    evening_id = _schedule(client, site_id, "16:00", "00:00")
    picked_id = _schedule(client, _site(client, "chsld"), "08:00", "16:00", period="jour", day=date(2026, 10, 20))
    patient = await _seed_patient()
    encounter_id = _push(client, patient, service_date=TUESDAY, time_start="20:00")
    client.put(f"/encounters/{encounter_id}/shift", json={"shift_id": picked_id})
    assert client.delete(f"/shifts/{picked_id}").status_code == 204

    setting = client.get(f"/encounters/{encounter_id}").json()["setting"]
    assert setting["shift"]["id"] == evening_id
    assert setting["shift_picked"] is False


async def test_picking_refuses_an_unknown_shift_or_encounter(me, client):
    patient = await _seed_patient()
    encounter_id = _push(client, patient, service_date=TUESDAY)
    assert client.put(f"/encounters/{encounter_id}/shift", json={"shift_id": 999_999}).status_code == 404
    shift_id = _schedule(client, _site(client), "16:00", "00:00")
    assert client.put("/encounters/999999/shift", json={"shift_id": shift_id}).status_code == 404


async def test_a_paste_from_a_shift_stores_the_pick(me, client):
    shift_id = _schedule(client, _site(client), "16:00", "00:00")
    [outcome] = _paste(client, _note_text("ZZZZ99999999"), shift_id=shift_id).json()

    async with session_scope() as session:
        encounter = await session.get(Encounter, outcome["encounter_id"])
    assert encounter.shift_id == shift_id
    setting = client.get(f"/encounters/{outcome['encounter_id']}").json()["setting"]
    assert setting["shift_picked"] is True
    assert setting["care_setting"] == "urgence"


def test_a_paste_refuses_a_shift_that_is_not_the_physicians(me, client):
    response = client.post("/intake/notes", json={"text": _note_text("ZZZZ99999999"), "shift_id": 999_999})
    assert response.status_code == 422
