"""Exercises the patients CRUD API. Most tests rely on conftest.py's
default_authenticated_user override (fake physician id=1); the ownership-scoping test
swaps in a second fake physician to prove patients aren't visible across physicians."""

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
    "is_registered_with_physician": True,
    "is_vulnerable": False,
}

# The test DB is shared (session-scoped file, not reset per test — see conftest.py), and
# almost every test here is physician id=1 — so each created patient needs its own NAM to
# avoid tripping ix_patients_physician_ramq_number_active (models.py) against an earlier
# test's still-active patient. Tests that care about the duplicate-NAM behavior itself
# pass an explicit ramq_number instead of using this default.
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


def test_create_patient_then_appears_in_list():
    payload = _valid_patient()
    with TestClient(app) as client:
        create_response = client.post("/patients", json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["full_name"] == "Jean Tremblay"
        assert created["ramq_number"] == payload["ramq_number"]

        list_response = client.get("/patients")

    assert list_response.status_code == 200
    assert any(p["id"] == created["id"] for p in list_response.json())


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


def test_update_patient():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        response = client.patch(
            f"/patients/{created['id']}",
            json={**created, "full_name": "Jean-Pierre Tremblay", "is_vulnerable": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Jean-Pierre Tremblay"
    assert body["is_vulnerable"] is True


def test_delete_patient_then_404():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        delete_response = client.delete(f"/patients/{created['id']}")
        get_response = client.get(f"/patients/{created['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_deleted_patient_is_soft_deleted_and_absent_from_list():
    # Soft delete (deleted_at timestamp), not a row removal — billing history must still be able
    # to resolve the patient's name after they leave the roster (see billing tests).
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.delete(f"/patients/{created['id']}")
        list_response = client.get("/patients")
        get_response = client.get(f"/patients/{created['id']}")

    assert all(p["id"] != created["id"] for p in list_response.json())
    assert get_response.status_code == 404


def test_deleting_already_deleted_patient_returns_404():
    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()
        client.delete(f"/patients/{created['id']}")
        second_delete = client.delete(f"/patients/{created['id']}")

    assert second_delete.status_code == 404


def test_re_adding_the_same_nam_after_a_soft_delete_succeeds():
    # The unique index (ix_patients_physician_ramq_number_active, models.py) is partial —
    # scoped to active rows — precisely so this doesn't collide with the row it replaces.
    payload = _valid_patient()
    with TestClient(app) as client:
        first = client.post("/patients", json=payload).json()
        client.delete(f"/patients/{first['id']}")
        second_response = client.post("/patients", json=payload)

    assert second_response.status_code == 201
    assert second_response.json()["ramq_number"] == payload["ramq_number"]


def test_creating_a_second_active_patient_with_the_same_nam_is_409():
    payload = _valid_patient()
    with TestClient(app) as client:
        first_response = client.post("/patients", json=payload)
        second_response = client.post("/patients", json={**payload, "full_name": "Jean Tremblay Deux"})

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_creating_two_patients_with_no_nam_does_not_collide():
    with TestClient(app) as client:
        first_response = client.post("/patients", json=_valid_patient(ramq_number=None))
        second_response = client.post("/patients", json=_valid_patient(ramq_number=None, full_name="Deux"))

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_updating_a_patient_to_another_active_patients_nam_is_409():
    with TestClient(app) as client:
        first = client.post("/patients", json=_valid_patient()).json()
        second = client.post("/patients", json=_valid_patient()).json()
        response = client.patch(f"/patients/{second['id']}", json={**second, "ramq_number": first["ramq_number"]})

    assert response.status_code == 409


async def test_deleted_patient_name_still_shows_on_an_existing_claim():
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
        claim = client.post(
            "/claims",
            json={
                "patient_id": created["id"],
                "service_date": "2026-02-10",
                "billing_extraction_record_id": extraction_record.id,
                "selected_codes": ["TEST-BP-MGMT"],
                "source_system": "simule",
            },
        ).json()

        client.delete(f"/patients/{created['id']}")
        claim_list = client.get("/claims").json()

    record = next(r for r in claim_list if r["id"] == claim["id"])
    assert record["patient_full_name"] == "Jean Tremblay"


def test_create_patient_missing_required_field_returns_422():
    with TestClient(app) as client:
        response = client.post("/patients", json=_valid_patient(date_of_birth=None))

    assert response.status_code == 422


def test_patient_not_visible_to_a_different_physician():
    other_physician = _other_physician()

    with TestClient(app) as client:
        created = client.post("/patients", json=_valid_patient()).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_response = client.get(f"/patients/{created['id']}")
            update_response = client.patch(f"/patients/{created['id']}", json=created)
            delete_response = client.delete(f"/patients/{created['id']}")
            list_response = client.get("/patients")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert get_response.status_code == 404
    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    assert all(p["id"] != created["id"] for p in list_response.json())


def test_patients_routes_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        assert client.get("/patients").status_code == 401
        assert client.post("/patients", json=VALID_PATIENT).status_code == 401
        assert client.get("/patients/1").status_code == 401
        assert client.patch("/patients/1", json=VALID_PATIENT).status_code == 401
        assert client.delete("/patients/1").status_code == 401
