"""Exercises the patients CRUD/search API and the physician's own optional roster.
Most tests rely on conftest.py's default_authenticated_user override (fake physician
id=1, role=PHYSICIAN). A separate fake admin user proves PATCH /patients/{id} (editing the
shared global record) is admin-only, and a second fake physician proves a patient created
by one physician is a *global* record — visible/searchable by anyone, not scoped like the
old per-physician roster was."""

import itertools

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, User, UserRole

VALID_PATIENT = {
    "full_name": "Jean Tremblay",
    "ramq_number": "TREJ12345678",
    "date_of_birth": "1980-05-12",
    "gender": "M",
    "is_vulnerable": False,
    "family_doctor_name": "Dr. Ex Ample",
    "family_doctor_practice_number": "123456",
}

# The test DB is shared (session-scoped file, not reset per test — see conftest.py), so each
# created patient needs its own NAM to avoid tripping ix_patients_ramq_number_active
# (models.py) against an earlier test's still-active patient. Tests that care about the
# duplicate-NAM behavior itself pass an explicit ramq_number instead of using this default.
_ramq_numbers = itertools.count(1)


def _valid_patient(**overrides):
    return {**VALID_PATIENT, "ramq_number": f"TREJ{next(_ramq_numbers):08d}", **overrides}


def _other_physician():
    return User(
        id=2,
        email="other-physician@example.test",
        full_name="Dr. Other",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )


def _admin():
    return User(
        id=3,
        email="admin@example.test",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )


def test_create_patient_returns_the_submitted_fields():
    payload = _valid_patient()
    with TestClient(app) as client:
        response = client.post("/patients", json=payload)

    assert response.status_code == 201
    created = response.json()
    assert created["full_name"] == "Jean Tremblay"
    assert created["ramq_number"] == payload["ramq_number"]
    assert created["family_doctor_name"] == "Dr. Ex Ample"


def test_created_patient_is_not_automatically_on_the_creators_roster():
    # Creating a global patient and adding them to "my patients" are two separate actions
    # now — see POST /patients/roster.
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        roster_response = client.get("/patients")

    assert all(p["id"] != created["id"] for p in roster_response.json())


def test_get_patient_by_id():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        response = client.get(f"/patients/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_patient_returns_404():
    with TestClient(app) as client:
        response = client.get("/patients/999999")

    assert response.status_code == 404


def test_patient_created_by_one_physician_is_visible_to_another():
    # The whole point of the global refactor: no per-physician ownership check gates reads.
    other_physician = _other_physician()

    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_response = client.get(f"/patients/{created['id']}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


def test_search_by_partial_name():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient(full_name="Zzyzx Uncommonname")).json()
        response = client.get("/patients/search", params={"q": "uncommonname"})

    assert response.status_code == 200
    assert any(p["id"] == created["id"] for p in response.json())


def test_search_by_nam():
    with TestClient(app) as client:
        payload = _valid_patient()
        created = client.post("/patients", json=payload).json()
        response = client.get("/patients/search", params={"q": payload["ramq_number"]})

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [created["id"]]


def test_search_below_minimum_length_returns_empty_not_an_error():
    with TestClient(app) as client:
        response = client.get("/patients/search", params={"q": "a"})

    assert response.status_code == 200
    assert response.json() == []


def test_create_patient_missing_required_field_returns_422():
    with TestClient(app) as client:
        response = client.post("/patients", json=_valid_patient(date_of_birth=None))

    assert response.status_code == 422


def test_invalid_practice_number_shape_returns_422():
    with TestClient(app) as client:
        response = client.post("/patients", json=_valid_patient(family_doctor_practice_number="12"))

    assert response.status_code == 422


def test_creating_a_second_active_patient_with_the_same_nam_is_409():
    payload = _valid_patient()
    with TestClient(app) as client:
        first_response = client.post("/patients", json=payload)
        second_response = client.post("/patients", json={**payload, "full_name": "Jean Tremblay Deux"})

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_creating_the_same_nam_from_a_different_physician_is_also_409():
    # Uniqueness is global now, not per-physician — a second physician can't create a
    # duplicate identity for the same real person either.
    payload = _valid_patient()
    other_physician = _other_physician()

    with TestClient(app) as client:
        first_response = client.post("/patients", json=payload)

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            second_response = client.post("/patients", json={**payload, "full_name": "Jean Tremblay Deux"})
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_creating_two_patients_with_no_nam_does_not_collide():
    with TestClient(app) as client:
        first_response = client.post("/patients", json=_valid_patient(ramq_number=None))
        second_response = client.post("/patients", json=_valid_patient(ramq_number=None, full_name="Deux"))

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_update_patient_requires_admin():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        response = client.patch(f"/patients/{created['id']}", json={**created, "full_name": "Renommé"})

    assert response.status_code == 403


def test_update_patient_as_admin_succeeds():
    admin = _admin()
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            response = client.patch(
                f"/patients/{created['id']}",
                json={**created, "full_name": "Jean-Pierre Tremblay", "is_vulnerable": True},
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Jean-Pierre Tremblay"
    assert body["is_vulnerable"] is True


def test_updating_a_patient_to_another_active_patients_nam_is_409():
    admin = _admin()
    with TestClient(app) as client:
        first = client.post("/patients", json=_valid_patient()).json()
        second = client.post("/patients", json=_valid_patient()).json()

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            response = client.patch(
                f"/patients/{second['id']}", json={**second, "ramq_number": first["ramq_number"]}
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 409


def test_add_to_roster_then_appears_in_list():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        add_response = client.post("/patients/roster", json={"patient_id": created["id"], "notes": "Suivi mensuel"})
        list_response = client.get("/patients")

    assert add_response.status_code == 201
    assert add_response.json()["notes"] == "Suivi mensuel"
    assert any(p["id"] == created["id"] for p in list_response.json())


def test_add_unknown_patient_to_roster_is_404():
    with TestClient(app) as client:
        response = client.post("/patients/roster", json={"patient_id": 999999})

    assert response.status_code == 404


def test_adding_the_same_patient_to_roster_twice_is_409():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.post("/patients/roster", json={"patient_id": created["id"]})
        second = client.post("/patients/roster", json={"patient_id": created["id"]})

    assert second.status_code == 409


def test_update_roster_entry_notes():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.post("/patients/roster", json={"patient_id": created["id"]})
        response = client.patch(f"/patients/roster/{created['id']}", json={"notes": "Allergie pénicilline"})

    assert response.status_code == 200
    assert response.json()["notes"] == "Allergie pénicilline"


def test_update_roster_entry_not_on_roster_is_404():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        response = client.patch(f"/patients/roster/{created['id']}", json={"notes": "x"})

    assert response.status_code == 404


def test_remove_from_roster_then_absent_from_list_but_still_searchable():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.post("/patients/roster", json={"patient_id": created["id"]})

        delete_response = client.delete(f"/patients/roster/{created['id']}")
        list_response = client.get("/patients")
        get_response = client.get(f"/patients/{created['id']}")

    assert delete_response.status_code == 204
    assert all(p["id"] != created["id"] for p in list_response.json())
    assert get_response.status_code == 200


def test_removing_from_roster_twice_returns_404_second_time():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.post("/patients/roster", json={"patient_id": created["id"]})
        client.delete(f"/patients/roster/{created['id']}")
        second_delete = client.delete(f"/patients/roster/{created['id']}")

    assert second_delete.status_code == 404


def test_roster_isolated_per_physician():
    # Two physicians can each roster the same global patient independently.
    other_physician = _other_physician()

    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.post("/patients/roster", json={"patient_id": created["id"]})

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            other_roster = client.get("/patients").json()
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert all(p["id"] != created["id"] for p in other_roster)


async def test_a_patient_not_on_the_billing_physicians_roster_can_still_be_claimed():
    # Claims are no longer roster-gated — the roster is optional personal metadata now,
    # not a billing prerequisite. See test_claims.py for the full claims-side coverage.
    billing_result = {
        "codes": [
            {
                "code": "TEST-BP-MGMT",
                "description": "Prise en charge d'une hypertension",
                "confidence": "high",
                "explanation": "hypertension artérielle depuis 10 ans",
                "fee": {"amount": 33.15, "when_to_use": "Par visite de suivi", "majoration": None},
            }
        ],
        "notes": None,
    }

    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        [extraction_record] = await ExtractionRepository().create_many(
            [
                ExtractionRecordInput(
                    task="billing_codes",
                    transcript="transcript de test",
                    result=billing_result,
                    model="mistral-small-latest",
                    source_system="simule",
                    user_id=1,
                )
            ]
        )
        claim_response = client.post(
            "/claims",
            json={
                "patient_id": created["id"],
                "service_date": "2026-02-10",
                "billing_extraction_record_id": extraction_record.id,
                "selected_codes": ["TEST-BP-MGMT"],
                "source_system": "simule",
            },
        )

    assert claim_response.status_code == 201


def test_patients_routes_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        assert client.get("/patients").status_code == 401
        assert client.post("/patients", json=VALID_PATIENT).status_code == 401
        assert client.get("/patients/1").status_code == 401
        assert client.get("/patients/search", params={"q": "ab"}).status_code == 401
        assert client.patch("/patients/1", json=VALID_PATIENT).status_code == 401
        assert client.post("/patients/roster", json={"patient_id": 1}).status_code == 401
        assert client.patch("/patients/roster/1", json={"notes": "x"}).status_code == 401
        assert client.delete("/patients/roster/1").status_code == 401
