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


def _series_body(site_id, **overrides):
    return {
        "work_site_id": site_id,
        "period": "jour",
        "start_date": "2026-12-07",
        "end_date": "2026-12-13",
        "start_time": "08:00",
        "end_time": "08:00",
        **overrides,
    }


def test_series_creates_one_shift_a_day():
    with TestClient(app) as client:
        site = _create_site(client, name="Garde hôpital", care_setting="hospitalisation")
        response = client.post("/shifts/series", json=_series_body(site["id"]))
        assert response.status_code == 201, response.text
        shifts = response.json()
        assert [s["service_date"] for s in shifts] == [f"2026-12-{d:02d}" for d in range(7, 14)]
        assert all(s["care_setting"] == "hospitalisation" and s["ends_next_day"] for s in shifts)


def test_series_weekdays_only():
    with TestClient(app) as client:
        site = _create_site(client, name="GMF Est", care_setting="gmf")
        shifts = client.post(
            "/shifts/series",
            json=_series_body(site["id"], start_date="2027-01-04", end_date="2027-01-17", end_time="16:00", weekdays_only=True),
        ).json()
        assert len(shifts) == 10
        assert {s["day_type"] for s in shifts} == {"semaine"}


def test_series_validation():
    with TestClient(app) as client:
        site = _create_site(client, name="GMF Ouest", care_setting="gmf")
        # A weekend only, weekdays only: nothing to schedule.
        weekend = _series_body(site["id"], start_date="2027-01-09", end_date="2027-01-10", weekdays_only=True)
        assert client.post("/shifts/series", json=weekend).status_code == 422
        backwards = _series_body(site["id"], start_date="2027-01-10", end_date="2027-01-09")
        assert client.post("/shifts/series", json=backwards).status_code == 422
        too_long = _series_body(site["id"], start_date="2027-01-01", end_date="2027-04-01")
        assert client.post("/shifts/series", json=too_long).status_code == 422


def _week_of(client, start, end):
    return client.get("/shifts", params={"start": start, "end": end}).json()


def test_single_shift_has_no_series():
    with TestClient(app) as client:
        site = _create_site(client, name="Urgence solo")
        assert client.post("/shifts", json=_shift_body(site["id"], service_date="2027-02-01")).json()["series_id"] is None


def test_edit_series_from_a_date_on():
    with TestClient(app) as client:
        site = _create_site(client, name="Garde série", care_setting="hospitalisation")
        shifts = client.post(
            "/shifts/series", json=_series_body(site["id"], start_date="2027-02-08", end_date="2027-02-12", end_time="16:00")
        ).json()
        series_id = shifts[0]["series_id"]
        assert series_id is not None and {s["series_id"] for s in shifts} == {series_id}

        response = client.put(
            f"/shifts/series/{series_id}",
            json={"work_site_id": site["id"], "period": "soir", "start_time": "16:00", "end_time": "00:00", "from_date": "2027-02-10"},
        )
        assert response.status_code == 200, response.text
        assert [s["service_date"] for s in response.json()] == ["2027-02-10", "2027-02-11", "2027-02-12"]

        week = _week_of(client, "2027-02-08", "2027-02-12")
        assert [(s["service_date"], s["period"]) for s in week if s["series_id"] == series_id] == [
            ("2027-02-08", "jour"),
            ("2027-02-09", "jour"),
            ("2027-02-10", "soir"),
            ("2027-02-11", "soir"),
            ("2027-02-12", "soir"),
        ]


def test_delete_series_whole_or_from_a_date():
    with TestClient(app) as client:
        site = _create_site(client, name="GMF série", care_setting="gmf")
        series_id = client.post(
            "/shifts/series", json=_series_body(site["id"], start_date="2027-03-01", end_date="2027-03-05", end_time="16:00")
        ).json()[0]["series_id"]

        assert client.delete(f"/shifts/series/{series_id}", params={"from_date": "2027-03-04"}).status_code == 204
        assert [s["service_date"] for s in _week_of(client, "2027-03-01", "2027-03-07")] == ["2027-03-01", "2027-03-02", "2027-03-03"]

        assert client.delete(f"/shifts/series/{series_id}").status_code == 204
        assert _week_of(client, "2027-03-01", "2027-03-07") == []
        assert client.delete(f"/shifts/series/{series_id}").status_code == 404


async def test_series_is_scoped_to_its_owner():
    other = User(id=97, email="other-series@example.test", full_name="Dr. Série", role=UserRole.PHYSICIAN, is_active=True)
    await ensure_user_row(other)
    with TestClient(app) as client:
        site = _create_site(client, name="Urgence série privée")
        series_id = client.post(
            "/shifts/series", json=_series_body(site["id"], start_date="2027-04-05", end_date="2027-04-06")
        ).json()[0]["series_id"]

        app.dependency_overrides[get_current_user] = lambda: other
        assert client.delete(f"/shifts/series/{series_id}").status_code == 404
        body = {"work_site_id": site["id"], "period": "soir", "start_time": "16:00", "end_time": "00:00"}
        assert client.put(f"/shifts/series/{series_id}", json=body).status_code == 404
