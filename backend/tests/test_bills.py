"""Exercises the /bills API end-to-end: create from a set of brouillon claims ->
list -> get detail -> download PDF -> delete, plus ownership scoping and the
empty-selection/stale-selection validation in app/bills/service.py."""

from datetime import date

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, Gender, PatientRepository, User, UserRole

BILLING_RESULT = {
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


def _other_physician():
    return User(
        id=99,
        email="other-physician-bills@example.test",
        full_name="Dr. Other",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )


async def _seed_patient(physician_id=1, full_name="Roch Desjardins", ramq_number="DESR81021001"):
    return await PatientRepository().create(
        physician_id=physician_id,
        full_name=full_name,
        ramq_number=ramq_number,
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_registered_with_physician=True,
        is_vulnerable=False,
    )


async def _seed_extraction_record(*, user_id=1, result=None):
    [record] = await ExtractionRepository().create_many(
        [
            ExtractionRecordInput(
                task="billing_codes",
                transcript="transcript de test",
                result=result if result is not None else BILLING_RESULT,
                model="mistral-small-latest",
                source_system="simule",
                user_id=user_id,
            )
        ]
    )
    return record


async def _seed_claim(client, *, patient_id, service_date="2026-02-10"):
    extraction_record = await _seed_extraction_record()
    response = client.post(
        "/claims",
        json={
            "patient_id": patient_id,
            "service_date": service_date,
            "billing_extraction_record_id": extraction_record.id,
            "selected_codes": ["TEST-BP-MGMT"],
            "source_system": "simule",
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_create_then_list_then_get_then_pdf_then_delete():
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim_a = await _seed_claim(client, patient_id=patient.id, service_date="2026-02-10")
        claim_b = await _seed_claim(client, patient_id=patient.id, service_date="2026-02-15")

        create_response = client.post(
            "/bills",
            json={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "claim_ids": [claim_a["id"], claim_b["id"]],
            },
        )
        assert create_response.status_code == 201
        bill = create_response.json()
        assert bill["number"] == f"FACT-{bill['id']:06d}"
        assert bill["record_count"] == 2
        assert bill["total_amount"] == 66.30

        list_response = client.get("/bills")
        assert list_response.status_code == 200
        assert any(b["id"] == bill["id"] for b in list_response.json())

        detail_response = client.get(f"/bills/{bill['id']}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert {c["id"] for c in detail["claims"]} == {claim_a["id"], claim_b["id"]}
        assert all(c["status"] == "soumis" for c in detail["claims"])

        pdf_response = client.get(f"/bills/{bill['id']}/pdf")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"] == "application/pdf"
        assert pdf_response.content.startswith(b"%PDF-")

        delete_response = client.delete(f"/bills/{bill['id']}")
        assert delete_response.status_code == 204

        assert client.get(f"/bills/{bill['id']}").status_code == 404
        claims_after_delete = client.get("/claims", params={"status": "brouillon"}).json()
        assert {claim_a["id"], claim_b["id"]} <= {c["id"] for c in claims_after_delete}


async def test_empty_selection_is_422():
    with TestClient(app) as client:
        response = client.post(
            "/bills", json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": []}
        )
    assert response.status_code == 422


async def test_submitting_an_already_billed_claim_is_409():
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim = await _seed_claim(client, patient_id=patient.id)

        first = client.post(
            "/bills",
            json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": [claim["id"]]},
        )
        assert first.status_code == 201

        second = client.post(
            "/bills",
            json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": [claim["id"]]},
        )
    assert second.status_code == 409


async def test_another_physicians_claim_id_is_409():
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim = await _seed_claim(client, patient_id=patient.id)

        app.dependency_overrides[get_current_user] = _other_physician
        try:
            response = client.post(
                "/bills",
                json={
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-28",
                    "claim_ids": [claim["id"]],
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 409


async def test_cross_physician_access_is_404():
    other_physician = _other_physician()

    with TestClient(app) as client:
        patient = await _seed_patient()
        claim = await _seed_claim(client, patient_id=patient.id)
        bill = client.post(
            "/bills",
            json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": [claim["id"]]},
        ).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_response = client.get(f"/bills/{bill['id']}")
            pdf_response = client.get(f"/bills/{bill['id']}/pdf")
            delete_response = client.delete(f"/bills/{bill['id']}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert get_response.status_code == 404
    assert pdf_response.status_code == 404
    assert delete_response.status_code == 404
