"""Work sites and shifts: the holiday calendar and day types, shift hours across midnight, and
the /work-sites and /shifts API (ownership, care-setting snapshot, voiding)."""

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.postgresdb import User, UserRole
from app.shifts import DayType, DayTypeResolver, ShiftHours
from app.shifts.holidays import QuebecHolidays
from tests.db_helpers import ensure_user_row


@pytest.mark.parametrize(
    ("day", "name"),
    [
        (date(2026, 4, 3), "Vendredi saint"),
        (date(2026, 4, 6), "Lundi de Pâques"),
        (date(2026, 5, 18), "Fête de Dollard"),
        (date(2025, 5, 19), "Fête de Dollard"),
        (date(2026, 9, 7), "Fête du Travail"),
        (date(2026, 10, 12), "Action de grâces"),
        (date(2027, 3, 26), "Vendredi saint"),
        (date(2026, 1, 2), "Lendemain du Jour de l'An"),
        (date(2026, 12, 31), "Veille du Jour de l'An"),
    ],
)
def test_holiday_dates(day, name):
    assert QuebecHolidays().name(day) == name


def test_thirteen_holidays_a_year():
    assert len(QuebecHolidays.for_year(2026)) == 13


def test_fete_de_dollard_is_the_monday_before_may_25_even_when_the_25th_is_a_monday():
    # May 25, 2026 is a Monday: Dollard is the Monday before, not the 25th itself.
    assert QuebecHolidays().name(date(2026, 5, 18)) == "Fête de Dollard"
    assert QuebecHolidays().name(date(2026, 5, 25)) is None


def test_day_type():
    resolver = DayTypeResolver()
    assert resolver.day_type(date(2026, 10, 27)) is DayType.SEMAINE
    assert resolver.day_type(date(2026, 10, 31)) is DayType.FIN_DE_SEMAINE
    # Saturday and a holiday: the holiday wins.
    assert resolver.day_type(date(2027, 12, 25)) is DayType.FERIE
    assert resolver.day_type(date(2026, 10, 12)) is DayType.FERIE


def test_shift_hours_cross_midnight():
    evening = ShiftHours(date(2026, 10, 27), time(16), time(0))
    assert evening.ends_next_day
    assert evening.duration == timedelta(hours=8)

    day = ShiftHours(date(2026, 10, 27), time(8), time(16))
    assert not day.ends_next_day
    assert day.ends_at.date() == date(2026, 10, 27)

    full_day = ShiftHours(date(2026, 10, 27), time(8), time(8))
    assert full_day.duration == timedelta(hours=24)


def _create_site(client, name="Urgence Hôpital Test", care_setting="urgence"):
    response = client.post("/work-sites", json={"name": name, "care_setting": care_setting})
    assert response.status_code == 201, response.text
    return response.json()


def _shift_body(site_id, **overrides):
    return {
        "work_site_id": site_id,
        "period": "soir",
        "service_date": "2026-10-27",
        "start_time": "16:00",
        "end_time": "00:00",
        **overrides,
    }


def test_site_care_setting_must_be_schedulable():
    with TestClient(app) as client:
        response = client.post("/work-sites", json={"name": "Domicile", "care_setting": "domicile"})
        assert response.status_code == 422


def test_create_and_list_shift():
    with TestClient(app) as client:
        site = _create_site(client)
        response = client.post("/shifts", json=_shift_body(site["id"]))
        assert response.status_code == 201, response.text
        shift = response.json()
        assert shift["care_setting"] == "urgence"
        assert shift["work_site_name"] == "Urgence Hôpital Test"
        assert shift["ends_next_day"] is True
        assert shift["day_type"] == "semaine"

        listed = client.get("/shifts", params={"start": "2026-10-26", "end": "2026-11-01"}).json()
        assert shift["id"] in [s["id"] for s in listed]
        outside = client.get("/shifts", params={"start": "2026-11-02", "end": "2026-11-08"}).json()
        assert shift["id"] not in [s["id"] for s in outside]


def test_list_range_is_bounded():
    with TestClient(app) as client:
        assert client.get("/shifts", params={"start": "2026-01-01", "end": "2026-06-01"}).status_code == 422
        assert client.get("/shifts", params={"start": "2026-02-01", "end": "2026-01-01"}).status_code == 422


def test_editing_a_site_keeps_its_shifts_care_setting():
    with TestClient(app) as client:
        site = _create_site(client, name="Hôpital A", care_setting="hospitalisation")
        shift = client.post("/shifts", json=_shift_body(site["id"], period="jour", start_time="08:00", end_time="16:00")).json()

        client.put(f"/work-sites/{site['id']}", json={"name": "Hôpital A", "care_setting": "chsld"})
        edited = client.put(f"/shifts/{shift['id']}", json=_shift_body(site["id"], period="jour", start_time="09:00", end_time="17:00"))
        assert edited.status_code == 200
        assert edited.json()["care_setting"] == "hospitalisation"
        assert edited.json()["start_time"] == "09:00:00"

        other = _create_site(client, name="GMF B", care_setting="gmf")
        moved = client.put(f"/shifts/{shift['id']}", json=_shift_body(other["id"], period="jour", start_time="09:00", end_time="17:00"))
        assert moved.json()["care_setting"] == "gmf"


def test_no_new_shift_on_a_deactivated_site():
    with TestClient(app) as client:
        site = _create_site(client, name="CHSLD fermé", care_setting="chsld")
        assert client.post(f"/work-sites/{site['id']}/deactivate").json()["is_active"] is False
        assert client.post("/shifts", json=_shift_body(site["id"])).status_code == 422
        assert site["id"] not in [s["id"] for s in client.get("/work-sites").json()]
        assert site["id"] in [s["id"] for s in client.get("/work-sites", params={"include_inactive": True}).json()]


def test_void_shift():
    with TestClient(app) as client:
        site = _create_site(client)
        shift = client.post("/shifts", json=_shift_body(site["id"], service_date="2026-11-03")).json()
        assert client.delete(f"/shifts/{shift['id']}").status_code == 204
        listed = client.get("/shifts", params={"start": "2026-11-01", "end": "2026-11-07"}).json()
        assert shift["id"] not in [s["id"] for s in listed]
        assert client.delete(f"/shifts/{shift['id']}").status_code == 404


async def test_sites_and_shifts_are_scoped_to_their_owner():
    other = User(id=98, email="other-shifts@example.test", full_name="Dr. Autre", role=UserRole.PHYSICIAN, is_active=True)
    await ensure_user_row(other)
    with TestClient(app) as client:
        site = _create_site(client, name="Urgence privée")
        shift = client.post("/shifts", json=_shift_body(site["id"], service_date="2026-11-10")).json()

        app.dependency_overrides[get_current_user] = lambda: other
        assert site["id"] not in [s["id"] for s in client.get("/work-sites").json()]
        assert client.post("/shifts", json=_shift_body(site["id"])).status_code == 422
        assert client.put(f"/shifts/{shift['id']}", json=_shift_body(site["id"])).status_code == 404
        assert client.delete(f"/shifts/{shift['id']}").status_code == 404
        assert client.post(f"/work-sites/{site['id']}/deactivate").status_code == 404


def test_period_defaults():
    with TestClient(app) as client:
        periods = {p["period"]: p for p in client.get("/shifts/periods").json()}
        assert periods["soir"]["start_time"] == "16:00:00"
        assert periods["soir"]["end_time"] == "00:00:00"
