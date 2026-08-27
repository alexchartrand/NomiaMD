"""Exercises the patients CRUD API. Most tests rely on conftest.py's
default_authenticated_user override (fake physician id=1); the ownership-scoping test
swaps in a second fake physician to prove patients aren't visible across physicians."""

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


def _other_physician():
    return User(
        id=2,
        email="other-physician@example.test",
        full_name="Dr. Other",
        role=UserRole.PHYSICIAN,
        physician_type=None,
        number_of_patients=None,
        remuneration_type=None,
        is_active=True,
    )


def test_create_patient_then_appears_in_list():
    with TestClient(app) as client:
        create_response = client.post("/patients", json=VALID_PATIENT)
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["full_name"] == "Jean Tremblay"
        assert created["ramq_number"] == "TREJ12345678"

        list_response = client.get("/patients")

    assert list_response.status_code == 200
    assert any(p["id"] == created["id"] for p in list_response.json())


def test_get_patient_by_id():
    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
        response = client.get(f"/patients/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_patient_returns_404():
    with TestClient(app) as client:
        response = client.get("/patients/999999")

    assert response.status_code == 404


def test_update_patient():
    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
        response = client.patch(
            f"/patients/{created['id']}",
            json={**VALID_PATIENT, "full_name": "Jean-Pierre Tremblay", "is_vulnerable": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Jean-Pierre Tremblay"
    assert body["is_vulnerable"] is True


def test_delete_patient_then_404():
    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
        delete_response = client.delete(f"/patients/{created['id']}")
        get_response = client.get(f"/patients/{created['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_deleted_patient_is_soft_deleted_and_absent_from_list():
    # Soft delete (is_deleted flag), not a row removal — billing history must still be able
    # to resolve the patient's name after they leave the roster (see billing tests).
    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
        client.delete(f"/patients/{created['id']}")
        list_response = client.get("/patients")
        get_response = client.get(f"/patients/{created['id']}")

    assert all(p["id"] != created["id"] for p in list_response.json())
    assert get_response.status_code == 404


def test_deleting_already_deleted_patient_returns_404():
    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
        client.delete(f"/patients/{created['id']}")
        second_delete = client.delete(f"/patients/{created['id']}")

    assert second_delete.status_code == 404


async def test_deleted_patient_name_still_shows_on_an_existing_claim():
    billing_result = {
        "codes": [
            {
                "code": "TEST-BP-MGMT",
                "description": "Prise en charge d'une hypertension",
                "confidence": 0.9,
                "explanation": "hypertension artérielle depuis 10 ans",
                "fee": {"amount": 33.15, "when_to_use": "Par visite de suivi", "majoration": None},
            }
        ],
        "notes": None,
    }

    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()
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
        response = client.post("/patients", json={**VALID_PATIENT, "date_of_birth": None})

    assert response.status_code == 422


def test_patient_not_visible_to_a_different_physician():
    other_physician = _other_physician()

    with TestClient(app) as client:
        created = client.post("/patients", json=VALID_PATIENT).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_response = client.get(f"/patients/{created['id']}")
            update_response = client.patch(f"/patients/{created['id']}", json=VALID_PATIENT)
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
