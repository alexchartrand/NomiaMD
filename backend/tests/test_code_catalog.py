"""Exercises the hand code search and lookup (GET /codes/search, GET /codes/{number}) over the
fixture codes (tests/fixtures/reference_data_test.json via conftest's StubCodeRepository),
plus CodeQueryParser on its own."""

import itertools
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.code_catalog.query import CodeQuery, CodeQueryKind, CodeQueryParser
from app.main import app
from app.postgresdb import Gender, PatientRepository, User, UserRole, session_scope
from tests.db_helpers import ensure_user_row

_ramq_numbers = itertools.count(1)
_physician_ids = itertools.count(7100)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, CodeQuery(CodeQueryKind.EMPTY)),
        ("   ", CodeQuery(CodeQueryKind.EMPTY)),
        ("0070", CodeQuery(CodeQueryKind.NUMBER_PREFIX, "0070")),
        (" 15801 ", CodeQuery(CodeQueryKind.NUMBER_PREFIX, "15801")),
        ("158012", CodeQuery(CodeQueryKind.TEXT, "158012")),
        ("suture plaie", CodeQuery(CodeQueryKind.TEXT, "suture plaie")),
        ("15801 visite", CodeQuery(CodeQueryKind.TEXT, "15801 visite")),
    ],
)
def test_parser(raw, expected):
    assert CodeQueryParser().parse(raw) == expected


async def _seed_patient(*, date_of_birth=date(1981, 2, 10)):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name="Luc Gagnon",
            ramq_number=f"GAGL{next(_ramq_numbers):08d}",
            date_of_birth=date_of_birth,
            gender=Gender.MALE,
            is_vulnerable=False,
        )


def _numbers(response) -> list[str]:
    assert response.status_code == 200
    return [hit["number"] for hit in response.json()]


async def test_search_by_description():
    with TestClient(app) as client:
        response = client.get("/codes/search", params={"q": "suture"})

    assert _numbers(response) == ["00059"]
    [hit] = response.json()
    assert hit["header_path"].startswith("C — ")
    assert hit["fees"][0]["amount"] == 25.0
    assert hit["needs_confirmation"] == []


async def test_search_by_number_prefix_in_number_order():
    with TestClient(app) as client:
        assert _numbers(client.get("/codes/search", params={"q": "158"})) == ["15801", "15802"]
        assert _numbers(client.get("/codes/search", params={"q": "158", "limit": 1})) == ["15801"]


async def test_without_a_patient_every_code_is_offered():
    with TestClient(app) as client:
        assert "09090" in _numbers(client.get("/codes/search", params={"q": "visite"}))


async def test_with_a_patient_codes_they_are_ineligible_for_are_hidden():
    with TestClient(app) as client:
        adult = await _seed_patient()
        child = await _seed_patient(date_of_birth=date(2020, 5, 1))

        for_adult = _numbers(client.get("/codes/search", params={"q": "visite", "patient_id": adult.id}))
        for_child = _numbers(client.get("/codes/search", params={"q": "visite", "patient_id": child.id}))

    assert "09090" not in for_adult
    assert "09090" in for_child


async def test_age_is_taken_on_the_service_date():
    with TestClient(app) as client:
        teenager = await _seed_patient(date_of_birth=date(2008, 6, 1))

        before_18 = client.get(
            "/codes/search", params={"q": "enfant", "patient_id": teenager.id, "service_date": "2026-05-31"}
        )
        after_18 = client.get(
            "/codes/search", params={"q": "enfant", "patient_id": teenager.id, "service_date": "2026-06-01"}
        )

    assert _numbers(before_18) == ["09090"]
    assert _numbers(after_18) == []


async def test_axes_the_patients_context_cannot_resolve_need_confirmation():
    # Neither the patient nor the default physician has a practice number, and no profile is
    # on file: registration and panel size are unknown, and 15801 is bound on both.
    with TestClient(app) as client:
        patient = await _seed_patient()

        response = client.get("/codes/search", params={"q": "15801", "patient_id": patient.id})

    [hit] = response.json()
    assert len(hit["needs_confirmation"]) == 2
    assert any("inscription" in note for note in hit["needs_confirmation"])
    assert any("clientèle" in note for note in hit["needs_confirmation"])


async def test_empty_query_offers_the_physicians_most_billed_codes_first():
    # A physician of their own: the shared test DB holds other tests' claims under user 1.
    doctor = User(id=next(_physician_ids), email="freq@example.test", full_name="Dr. Freq", role=UserRole.PHYSICIAN, is_active=True)
    await ensure_user_row(doctor)
    app.dependency_overrides[get_current_user] = lambda: doctor
    try:
        with TestClient(app) as client:
            patient = await _seed_patient()

            def bill(*codes, service_date="2026-03-02"):
                payload = {
                    "patient_id": patient.id,
                    "service_date": service_date,
                    "selected_codes": [{"code": c} for c in codes],
                }
                response = client.post("/claims/manual", json=payload)
                assert response.status_code == 201
                return response.json()

            assert _numbers(client.get("/codes/search")) == []
            bill("15802", service_date="2026-03-01")
            bill("00059", "15802", service_date="2026-03-02")
            bill("00059", service_date="2026-03-05")
            voided = bill("15801", service_date="2026-03-06")
            client.delete(f"/claims/{voided['id']}")

            # Tied on count (2 each): the most recently billed first. The voided one is gone.
            assert _numbers(client.get("/codes/search")) == ["00059", "15802"]
            assert _numbers(client.get("/codes/search", params={"q": " "})) == ["00059", "15802"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_get_returns_a_codes_full_detail():
    with TestClient(app) as client:
        response = client.get("/codes/15801")

    assert response.status_code == 200
    detail = response.json()
    assert detail["number"] == "15801"
    assert detail["when_to_use"] == ["Visite périodique d'un patient inscrit"]
    assert detail["eligibility"]["max_panel_size"] == 499
    assert detail["eligibility"]["requires_registered"] is True
    assert [f["lieux"] for f in detail["fees"]] == [["cabinet"], ["domicile"]]


async def test_get_an_unknown_code_is_404():
    with TestClient(app) as client:
        response = client.get("/codes/99999")

    assert response.status_code == 404


def test_search_limit_is_bounded():
    with TestClient(app) as client:
        assert client.get("/codes/search", params={"limit": 51}).status_code == 422
