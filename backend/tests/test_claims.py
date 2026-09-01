"""Exercises the /claims API end-to-end: create -> list -> filter -> delete, plus
ownership scoping and the validation/duplicate rules in app/claims/service.py. Status is
read-only from this API (no PATCH) — a claim only leaves "brouillon" via POST /bills, see
test_deleting_a_claim_on_a_bill_is_409 and tests/test_bills.py.
"""

import itertools
import json
from datetime import date

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, Gender, PatientRepository, User, UserRole

# The test DB is shared (session-scoped file, not reset per test — see conftest.py), and
# patients are globally unique by NAM now — so each seeded patient needs its own NAM to
# avoid tripping ix_patients_ramq_number_active (models.py) against an earlier test's
# still-active patient.
_ramq_numbers = itertools.count(1)

BILLING_RESULT = {
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une hypertension",
            "confidence": "high",
            "explanation": "hypertension artérielle depuis 10 ans",
            "fees": [{"amount": 33.15, "amount_text": "33,15", "context": "Par visite de suivi", "lieu": None, "majoration": None}],
        },
        {
            "code": "TEST-BLOODWORK-ORDER",
            "description": "Demande et révision d'un bilan sanguin de routine",
            "confidence": "medium",
            "explanation": "Bilan sanguin de contrôle demandé",
            "fees": [],
        },
    ],
    "notes": None,
}


def _other_physician():
    return User(
        id=99,
        email="other-physician@example.test",
        full_name="Dr. Other",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )


async def _seed_patient():
    return await PatientRepository().create(
        full_name="Roch Desjardins",
        ramq_number=f"DESR{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


async def _seed_extraction_record(*, user_id=1, result=None, task="billing_codes"):
    [record] = await ExtractionRepository().create_many(
        [
            ExtractionRecordInput(
                task=task,
                transcript="transcript de test",
                result=result if result is not None else BILLING_RESULT,
                model="mistral-small-latest",
                source_system="simule",
                user_id=user_id,
            )
        ]
    )
    return record


def _valid_payload(*, patient_id, billing_extraction_record_id, service_date="2026-02-10"):
    return {
        "patient_id": patient_id,
        "service_date": service_date,
        "billing_extraction_record_id": billing_extraction_record_id,
        "selected_codes": [{"code": "TEST-BP-MGMT", "fee_index": 0}],
        "source_system": "simule",
    }


async def test_create_then_list_then_filter_then_delete():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()

        create_response = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id),
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["patient_full_name"] == "Roch Desjardins"
        assert created["status"] == "brouillon"
        assert created["total_amount"] == 33.15
        assert [c["code"] for c in created["codes"]] == ["TEST-BP-MGMT"]

        list_response = client.get("/claims")
        assert list_response.status_code == 200
        assert any(r["id"] == created["id"] for r in list_response.json())

        filtered_by_patient = client.get("/claims", params={"patient_id": patient.id})
        assert [r["id"] for r in filtered_by_patient.json()] == [created["id"]]

        filtered_out_by_date = client.get("/claims", params={"date_from": "2026-03-01"})
        assert created["id"] not in [r["id"] for r in filtered_out_by_date.json()]

        filtered_by_status = client.get("/claims", params={"status": "brouillon"})
        assert created["id"] in [r["id"] for r in filtered_by_status.json()]
        filtered_by_wrong_status = client.get("/claims", params={"status": "soumis"})
        assert created["id"] not in [r["id"] for r in filtered_by_wrong_status.json()]

        delete_response = client.delete(f"/claims/{created['id']}")
        assert delete_response.status_code == 204
        list_after_delete = client.get("/claims")
        assert created["id"] not in [r["id"] for r in list_after_delete.json()]


async def test_deleting_a_claim_on_a_bill_is_409():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()
        created = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id),
        ).json()

        bill_response = client.post(
            "/bills",
            json={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "claim_ids": [created["id"]],
            },
        )
        assert bill_response.status_code == 201

        claim_after_billing = client.get("/claims", params={"status": "soumis"}).json()
        assert created["id"] in [r["id"] for r in claim_after_billing]

        delete_response = client.delete(f"/claims/{created['id']}")
        assert delete_response.status_code == 409


async def test_cross_physician_access_is_404():
    other_physician = _other_physician()

    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()
        created = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id),
        ).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_list = client.get("/claims")
            delete_response = client.delete(f"/claims/{created['id']}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert all(r["id"] != created["id"] for r in get_list.json())
    assert delete_response.status_code == 404


async def test_creating_a_claim_for_a_patient_not_on_the_billing_physicians_roster_succeeds():
    # Patients are a shared, global identity now — claiming one no longer requires having
    # added them to "my patients list" first (see app/postgresdb/models.py's Patient).
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()

        response = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id),
        )

    assert response.status_code == 201


async def test_creating_against_an_unknown_patient_is_404():
    with TestClient(app) as client:
        extraction_record = await _seed_extraction_record()

        response = client.post(
            "/claims",
            json=_valid_payload(patient_id=999999, billing_extraction_record_id=extraction_record.id),
        )

    assert response.status_code == 404


async def test_creating_against_another_physicians_extraction_record_is_404():
    with TestClient(app) as client:
        patient = await _seed_patient()
        other_physicians_extraction = await _seed_extraction_record(user_id=99)

        response = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=other_physicians_extraction.id),
        )

    assert response.status_code == 404


async def test_billing_extraction_record_id_pointing_at_a_summary_record_is_404():
    # get_for_user only checks ownership, not task type — swapping the ids in a request
    # (summary_extraction_record_id where billing_extraction_record_id belongs) must still
    # be rejected, not silently treated as "no candidate codes matched".
    with TestClient(app) as client:
        patient = await _seed_patient()
        summary_record = await _seed_extraction_record(
            task="consultation_summary", result={"short_description": "not a billing_codes result"}
        )

        response = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=summary_record.id),
        )

    assert response.status_code == 404


async def test_summary_extraction_record_id_owned_by_another_physician_is_404():
    with TestClient(app) as client:
        patient = await _seed_patient()
        billing_record = await _seed_extraction_record()
        other_physicians_summary = await _seed_extraction_record(user_id=99)

        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=billing_record.id)
        payload["summary_extraction_record_id"] = other_physicians_summary.id
        response = client.post("/claims", json=payload)

    assert response.status_code == 404


async def test_empty_selected_codes_is_422():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()

        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)
        payload["selected_codes"] = []
        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_code_absent_from_extraction_is_422():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()

        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)
        payload["selected_codes"] = [{"code": "NOT-A-CANDIDATE", "fee_index": 0}]
        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_selecting_a_fee_index_lands_that_variant_on_the_claim():
    with TestClient(app) as client:
        patient = await _seed_patient()
        multi_fee_result = {
            "codes": [
                {
                    "code": "TEST-BP-MGMT",
                    "description": "Prise en charge d'une hypertension",
                    "confidence": "high",
                    "explanation": "hypertension artérielle depuis 10 ans",
                    "fees": [
                        {"amount": 33.15, "amount_text": "33,15", "context": "Jour", "lieu": "Cabinet", "majoration": None},
                        {"amount": 40.0, "amount_text": "40,00", "context": "Soir", "lieu": "Domicile", "majoration": "20%"},
                    ],
                }
            ],
            "notes": None,
        }
        extraction_record = await _seed_extraction_record(result=multi_fee_result)
        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 1}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    [code] = response.json()["codes"]
    assert code["fee_amount"] == 40.0
    assert code["fee_when_to_use"] == "Soir — Domicile"
    assert code["majoration"] == "20%"


async def test_out_of_range_fee_index_is_422():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()
        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 5}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_second_save_of_same_extraction_is_409():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()
        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)

        first = client.post("/claims", json=payload)
        assert first.status_code == 201

        second = client.post("/claims", json=payload)

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_claim"


async def test_second_save_of_same_extraction_is_409_even_with_confirm_duplicate():
    with TestClient(app) as client:
        patient = await _seed_patient()
        extraction_record = await _seed_extraction_record()
        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)

        client.post("/claims", json=payload)
        second = client.post("/claims", json=payload, params={"confirm_duplicate": "true"})

    assert second.status_code == 409


async def test_same_patient_and_date_via_different_extraction_warns_then_allows_override():
    with TestClient(app) as client:
        patient = await _seed_patient()
        first_extraction = await _seed_extraction_record()
        second_extraction = await _seed_extraction_record()

        first = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=first_extraction.id),
        )
        assert first.status_code == 201

        blocked = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=second_extraction.id),
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "duplicate_claim"

        overridden = client.post(
            "/claims",
            json=_valid_payload(patient_id=patient.id, billing_extraction_record_id=second_extraction.id),
            params={"confirm_duplicate": "true"},
        )
        assert overridden.status_code == 201


async def test_deleting_a_claim_removes_its_code_rows_and_total_is_null_when_no_fees():
    with TestClient(app) as client:
        patient = await _seed_patient()
        no_fee_result = {
            "codes": [
                {
                    "code": "TEST-BLOODWORK-ORDER",
                    "description": "Demande et révision d'un bilan sanguin de routine",
                    "confidence": "medium",
                    "explanation": "Bilan sanguin de contrôle demandé",
                    "fees": [],
                }
            ],
            "notes": None,
        }
        extraction_record = await _seed_extraction_record(result=no_fee_result)
        payload = _valid_payload(patient_id=patient.id, billing_extraction_record_id=extraction_record.id)
        payload["selected_codes"] = [{"code": "TEST-BLOODWORK-ORDER", "fee_index": None}]

        created = client.post("/claims", json=payload).json()
        assert created["total_amount"] is None

        client.delete(f"/claims/{created['id']}")
        list_response = client.get("/claims")

    assert created["id"] not in [r["id"] for r in list_response.json()]
