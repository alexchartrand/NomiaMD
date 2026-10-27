"""Shift codes and shift claims: the curated catalog, the rules splitting a shift's hours
over each code's window and day types, fees by date, the /shifts/{id}/billing and
/shifts/{id}/claim API, billing shift claims next to patient claims, and the dashboard's
count of shifts left to claim."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import get_current_user
from app.care_setting import CareSetting
from app.clock import ClinicClock
from app.main import app
from app.shift_claims.catalog import ShiftCodeCatalog
from app.shift_claims.fees import ShiftFeeResolver
from app.shift_claims.rules import ShiftCodeRules
from app.shifts import ShiftHours
from tests.db_helpers import ensure_user_row, physician

CATALOG = ShiftCodeCatalog()
RULES = ShiftCodeRules(CATALOG)

TUESDAY = date(2026, 10, 27)
FRIDAY = date(2026, 10, 30)
SATURDAY = date(2026, 10, 31)
THANKSGIVING = date(2026, 10, 12)  # Action de grâces, a Monday


def _suggest(care_setting, day, start, end):
    lines = RULES.suggest(care_setting, ShiftHours(day, start, end))
    return {line.code.number: line.hours for line in lines}


def test_catalog_holds_the_er_supplements():
    assert {code.number for code in CATALOG.all()} == {"09791", "19953"}
    assert CATALOG.get("09791").citation == "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)"
    assert CATALOG.for_care_setting(CareSetting.GMF) == []


def test_catalog_refuses_duplicate_numbers(tmp_path):
    entry = """
  - number: "09791"
    description: x
    care_settings: [urgence]
    day_types: [semaine]
    window: {start: "20:00", end: "00:00"}
    quart_hours: 4
    divisible_in_hours: true
    fees: [{effective_from: 2019-10-01, per_quart: "156.40"}]
    source: {section: "P.G. 2.2.9 B", manual_rev: "2026-06-05"}
"""
    path = tmp_path / "codes.yaml"
    path.write_text("codes:" + entry + entry)
    with pytest.raises(ValidationError):
        ShiftCodeCatalog(path).all()


def test_weekday_evening_earns_four_hours_of_09791():
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(16), time(0)) == {"09791": 4}


def test_weekend_evening_earns_19953_from_8h():
    assert _suggest(CareSetting.URGENCE, SATURDAY, time(16), time(0)) == {"19953": 8}
    assert _suggest(CareSetting.URGENCE, SATURDAY, time(0), time(8)) == {}


def test_holiday_reads_as_a_weekend():
    assert _suggest(CareSetting.URGENCE, THANKSGIVING, time(8), time(16)) == {"19953": 8}
    assert _suggest(CareSetting.URGENCE, THANKSGIVING, time(16), time(0)) == {"19953": 8}


def test_each_hour_is_read_on_its_own_day():
    # Friday 18 h to Saturday 10 h: Friday 20–24 h is a weekday, Saturday 8–10 h a weekend.
    assert _suggest(CareSetting.URGENCE, FRIDAY, time(18), time(10)) == {"09791": 4, "19953": 2}


def test_weekday_day_and_night_shifts_earn_nothing():
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(8), time(16)) == {}
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(0), time(8)) == {}


def test_only_whole_hours_count():
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(20, 30), time(0)) == {"09791": 3}


def test_other_settings_earn_nothing():
    assert _suggest(CareSetting.GMF, TUESDAY, time(16), time(0)) == {}
    assert _suggest(None, TUESDAY, time(16), time(0)) == {}


def test_a_code_not_divisible_in_hours_counts_whole_quarts():
    code = CATALOG.get("09791").model_copy(update={"divisible_in_hours": False})
    assert ShiftCodeRules.billable_hours(code, 7 * 60) == 4
    assert ShiftCodeRules.billable_hours(code, 3 * 60) == 0


def test_fee_is_the_one_in_effect_on_the_shift_date():
    code = CATALOG.get("09791")
    current = ShiftFeeResolver.resolve(code, TUESDAY, 4)
    assert (current.hourly_fee, current.amount) == (Decimal("39.10"), Decimal("156.40"))
    assert ShiftFeeResolver.resolve(code, date(2018, 9, 15), 2).amount == Decimal("69.90")
    assert ShiftFeeResolver.resolve(code, date(2018, 8, 1), 4).amount is None


# --- API ---------------------------------------------------------------------------------

ME = 4242


@pytest.fixture
async def client():
    user = physician(ME)
    await ensure_user_row(user)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client


def _site(client, care_setting="urgence", name="Urgence Hôpital Test"):
    response = client.post("/work-sites", json={"name": name, "care_setting": care_setting})
    assert response.status_code == 201, response.text
    return response.json()


def _shift(client, site, *, day=TUESDAY, start="16:00", end="00:00", period="soir"):
    response = client.post(
        "/shifts",
        json={
            "work_site_id": site["id"],
            "period": period,
            "service_date": day.isoformat(),
            "start_time": start,
            "end_time": end,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_billing_shows_suggestions_and_available_codes(client):
    shift = _shift(client, _site(client))
    billing = client.get(f"/shifts/{shift['id']}/billing").json()
    assert billing["shift"]["id"] == shift["id"]
    assert billing["suggested"] == [
        {
            "code": "09791",
            "description": CATALOG.get("09791").description,
            "hours": 4,
            "hourly_fee": 39.10,
            "fee_amount": 156.40,
            "source": "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)",
        }
    ]
    assert [code["code"] for code in billing["available_codes"]] == ["09791", "19953"]
    assert billing["claim"] is None


def test_save_then_replace_a_draft(client):
    shift = _shift(client, _site(client))
    saved = client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09791", "hours": 4}]})
    assert saved.status_code == 200, saved.text
    claim = saved.json()
    assert claim["status"] == "brouillon"
    assert claim["total_amount"] == 156.40
    assert claim["work_site_name"] == "Urgence Hôpital Test"
    assert claim["ends_next_day"] is True
    assert claim["codes"][0]["origin"] == "suggested"

    # The établissement counts this Tuesday as a holiday: 19953 by hand.
    replaced = client.put(
        f"/shifts/{shift['id']}/claim",
        json={"codes": [{"code": "09791", "hours": 3}, {"code": "19953", "hours": 1}]},
    ).json()
    assert replaced["id"] != claim["id"]
    assert [(c["code"], c["origin"], c["fee_amount"]) for c in replaced["codes"]] == [
        ("09791", "suggested", 117.30),
        ("19953", "manual", 39.10),
    ]
    listed = client.get("/shift-claims").json()
    assert [c["id"] for c in listed if c["shift_id"] == shift["id"]] == [replaced["id"]]
    assert client.get(f"/shifts/{shift['id']}/billing").json()["claim"]["id"] == replaced["id"]


@pytest.mark.parametrize(
    ("codes", "detail"),
    [
        ([], "Au moins un code doit être sélectionné"),
        ([{"code": "15259", "hours": 1}], "Code 15259 non applicable à ce quart"),
        ([{"code": "09791", "hours": 9}], "Code 09791 : 9 h dépasse la durée du quart (8 h)"),
    ],
)
def test_save_refuses(client, codes, detail):
    shift = _shift(client, _site(client))
    response = client.put(f"/shifts/{shift['id']}/claim", json={"codes": codes})
    assert response.status_code == 422
    assert response.json()["detail"] == detail


def test_a_gmf_shift_has_no_shift_codes(client):
    shift = _shift(client, _site(client, care_setting="gmf", name="GMF Test"))
    billing = client.get(f"/shifts/{shift['id']}/billing").json()
    assert billing["suggested"] == [] and billing["available_codes"] == []
    assert client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09791", "hours": 4}]}).status_code == 422


def test_another_physicians_shift_is_404(client):
    shift = _shift(client, _site(client))
    other = physician(4243)
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get(f"/shifts/{shift['id']}/billing").status_code == 404
    assert client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09791", "hours": 4}]}).status_code == 404


def test_bill_a_shift_claim(client):
    shift = _shift(client, _site(client), day=SATURDAY)
    claim = client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "19953", "hours": 8}]}).json()

    bill = client.post(
        "/bills",
        json={"start_date": SATURDAY.isoformat(), "end_date": SATURDAY.isoformat(), "shift_claim_ids": [claim["id"]]},
    )
    assert bill.status_code == 201, bill.text
    bill = bill.json()
    assert (bill["claim_count"], bill["total_amount"]) == (1, 312.80)
    detail = client.get(f"/bills/{bill['id']}").json()
    assert detail["claims"] == []
    assert [(c["id"], c["status"]) for c in detail["shift_claims"]] == [(claim["id"], "soumis")]
    pdf = client.get(f"/bills/{bill['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")

    # Frozen while on the bill: neither the claim nor its shift can change.
    assert client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "19953", "hours": 4}]}).status_code == 409
    assert client.delete(f"/shift-claims/{claim['id']}").status_code == 409
    assert client.delete(f"/shifts/{shift['id']}").status_code == 409
    # Twice on bills: the second one is stale.
    again = client.post(
        "/bills",
        json={"start_date": SATURDAY.isoformat(), "end_date": SATURDAY.isoformat(), "shift_claim_ids": [claim["id"]]},
    )
    assert again.status_code == 409

    # Voiding the bill frees it.
    assert client.delete(f"/bills/{bill['id']}").status_code == 204
    assert claim["id"] in [c["id"] for c in client.get("/shift-claims", params={"status": "brouillon"}).json()]


def test_removing_a_shift_voids_its_draft(client):
    shift = _shift(client, _site(client), day=FRIDAY)
    claim = client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09791", "hours": 4}]}).json()
    assert client.delete(f"/shifts/{shift['id']}").status_code == 204
    assert claim["id"] not in [c["id"] for c in client.get("/shift-claims").json()]


async def test_dashboard_counts_past_shifts_left_to_claim(client):
    # Its own physician: the other tests' fixed-date shifts would fall in the window some day.
    user = physician(4244)
    await ensure_user_row(user)
    app.dependency_overrides[get_current_user] = lambda: user
    today = ClinicClock().today()
    site = _site(client)
    yesterday = _shift(client, site, day=today - timedelta(days=1))
    # Out of the count: a night shift (no shift code), today's shift, one past the deadline.
    _shift(client, site, day=today - timedelta(days=2), start="00:00", end="08:00", period="nuit")
    _shift(client, site, day=today)
    _shift(client, site, day=today - timedelta(days=120))

    assert client.get("/dashboard").json()["tasks"]["unclaimed_shifts"] == 1
    codes = client.get(f"/shifts/{yesterday['id']}/billing").json()["suggested"]
    client.put(f"/shifts/{yesterday['id']}/claim", json={"codes": [{"code": c["code"], "hours": c["hours"]} for c in codes]})
    assert client.get("/dashboard").json()["tasks"]["unclaimed_shifts"] == 0
