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
from app.shift_claims.catalog import GardeOption, ShiftCodeCatalog
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


def _suggest(care_setting, day, start, end, garde_option=GardeOption.ACTE):
    lines = RULES.suggest(care_setting, ShiftHours(day, start, end), garde_option)
    return {line.code.number: line.hours for line in lines}


def test_catalog_holds_the_er_supplements_and_garde_forfaits():
    assert {code.number for code in CATALOG.all()} == {
        "09791", "19953", "09998", "19055", "09996", "09994", "19056", "42265", "42266"
    }
    # À l'acte, only the supplements: the forfaits need the physician's choice.
    assert [code.number for code in CATALOG.for_care_setting(CareSetting.URGENCE)] == ["09791", "19953"]
    assert CATALOG.get("09791").citation == "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)"
    assert CATALOG.for_care_setting(CareSetting.GMF) == []
    assert {code.secteur_dispensation for code in CATALOG.all()} == {"07"}
    assert CATALOG.secteur_label("07") == "Service d'urgence"


_ENTRY = """
  - number: "09791"
    description: x
    care_settings: [urgence]
    day_types: [semaine]
    window: {start: "20:00", end: "00:00"}
    quart_hours: 4
    divisible_in_hours: true
    secteur_dispensation: "07"
    fees: [{effective_from: 2019-10-01, per_quart: "156.40"}]
    source: {section: "P.G. 2.2.9 B", manual_rev: "2026-06-05"}
"""


def test_catalog_refuses_duplicate_numbers(tmp_path):
    path = tmp_path / "codes.yaml"
    path.write_text('secteurs_dispensation: {"07": "Service d\'urgence"}\ncodes:' + _ENTRY + _ENTRY)
    with pytest.raises(ValidationError):
        ShiftCodeCatalog(path).all()


def test_catalog_refuses_an_unknown_secteur(tmp_path):
    path = tmp_path / "codes.yaml"
    path.write_text('secteurs_dispensation: {"32": "Service d\'urgence d\'un établissement"}\ncodes:' + _ENTRY)
    with pytest.raises(ValidationError, match="unknown secteur de dispensation 07"):
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


@pytest.mark.parametrize(
    ("garde_option", "day", "expected"),
    [
        (GardeOption.PREMIER, TUESDAY, {"09791": 4, "09996": 4, "09998": 8}),
        (GardeOption.SECOND, TUESDAY, {"09791": 4, "09994": 8}),
        (GardeOption.PARTAGE, TUESDAY, {"09791": 4, "09996": 4, "42265": 8}),
        # Friday 20 h to Saturday 8 h: the night is a weekend one.
        (GardeOption.PREMIER, FRIDAY, {"09791": 4, "09996": 4, "19055": 8}),
        (GardeOption.SECOND, FRIDAY, {"09791": 4, "19056": 8}),
        (GardeOption.PARTAGE, FRIDAY, {"09791": 4, "09996": 4, "42266": 8}),
    ],
)
def test_garde_forfaits_follow_the_physicians_option(garde_option, day, expected):
    assert _suggest(CareSetting.URGENCE, day, time(20), time(8), garde_option) == expected


def test_a_forfait_not_divisible_needs_its_whole_period():
    # 2 h to 8 h: the premier médecin's forfait isn't earned; a shared night's one is, by the hour.
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(2), time(8), GardeOption.PREMIER) == {}
    assert _suggest(CareSetting.URGENCE, TUESDAY, time(2), time(8), GardeOption.PARTAGE) == {"42265": 6}


def test_catalog_refuses_a_forfait_for_acte(tmp_path):
    path = tmp_path / "codes.yaml"
    path.write_text('secteurs_dispensation: {"07": "Service d\'urgence"}\ncodes:' + _ENTRY + "    garde_options: [acte]\n")
    with pytest.raises(ValidationError):
        ShiftCodeCatalog(path).all()


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
    assert ShiftFeeResolver.resolve(CATALOG.get("09998"), TUESDAY, 8).amount == Decimal("715.20")
    assert ShiftFeeResolver.resolve(CATALOG.get("42266"), TUESDAY, 3).amount == Decimal("326.85")


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
            "secteur_dispensation": "07",
            "secteur_dispensation_label": "Service d'urgence",
            "source": "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)",
        }
    ]
    assert [code["code"] for code in billing["available_codes"]] == ["09791", "19953"]
    assert billing["claim"] is None
    assert billing["garde_option"] == "acte"
    assert [choice["value"] for choice in billing["garde_choices"]] == ["acte", "premier", "second", "partage"]


def test_a_garde_forfait_is_saved_with_its_option(client):
    shift = _shift(client, _site(client), start="20:00", end="08:00", period="nuit")
    billing = client.get(f"/shifts/{shift['id']}/billing", params={"garde_option": "premier"}).json()
    assert [(c["code"], c["hours"], c["fee_amount"]) for c in billing["suggested"]] == [
        ("09791", 4, 156.40),
        ("09998", 8, 715.20),
        ("09996", 4, 174.85),
    ]
    # À l'acte, a forfait isn't billable; a forfait isn't by the hour.
    assert client.put(f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09998", "hours": 8}]}).status_code == 422
    partial = client.put(
        f"/shifts/{shift['id']}/claim", json={"codes": [{"code": "09996", "hours": 3}], "garde_option": "premier"}
    )
    assert partial.status_code == 422
    assert partial.json()["detail"] == "Code 09996 : par période complète de 4 h seulement"

    saved = client.put(
        f"/shifts/{shift['id']}/claim",
        json={"codes": [{"code": c["code"], "hours": c["hours"]} for c in billing["suggested"]], "garde_option": "premier"},
    ).json()
    assert saved["garde_option"] == "premier"
    assert saved["total_amount"] == 1046.45
    # Reopened, the shift reads under the option its claim was saved with.
    assert client.get(f"/shifts/{shift['id']}/billing").json()["garde_option"] == "premier"


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
    assert claim["codes"][0]["secteur_dispensation"] == "07"

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
    assert billing["suggested"] == [] and billing["available_codes"] == [] and billing["garde_choices"] == []
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
