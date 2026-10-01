"""Exercises the /bills API end-to-end: create from a set of brouillon claims ->
list -> get detail -> download PDF -> void, plus ownership scoping and the
empty-selection/stale-selection validation in app/bills/service.py."""

import itertools
from datetime import date

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.postgresdb import (
    Bill,
    ExtractionRepository,
    ExtractionRunInput,
    ExtractionStageInput,
    Gender,
    PatientRepository,
    User,
    UserRole,
    session_scope,
)

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
            "fees": [{"amount": 33.15, "amount_text": "33,15", "context": "Par visite de suivi", "lieux": [], "majoration": None}],
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


async def _seed_patient(full_name="Roch Desjardins", ramq_number=None):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            # Distinct prefix from test_claims.py's own _seed_patient — a shared prefix would
            # let their counters collide across files, since patients are globally unique by NAM.
            ramq_number=ramq_number or f"BILP{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )


async def _seed_run(patient_id, *, user_id=1, result=None):
    async with session_scope() as session:
        return await ExtractionRepository(session).create_run(
            ExtractionRunInput(
                user_id=user_id,
                patient_id=patient_id,
                transcript="transcript de test",
                source_system="simule",
                stages=[
                    ExtractionStageInput(
                        task="billing_codes",
                        model="mistral-small-latest",
                        result=result if result is not None else BILLING_RESULT,
                    )
                ],
            )
        )


async def _seed_claim(client, *, patient_id, service_date="2026-02-10", result=None):
    run = await _seed_run(patient_id, result=result)
    response = client.post(
        "/claims",
        json={
            "extraction_run_id": run.id,
            "service_date": service_date,
            "selected_codes": [{"code": "TEST-BP-MGMT", "fee_index": 0}],
        },
        # Several claims per patient per day across these tests — not what's under test here.
        params={"confirm_duplicate": "true"},
    )
    assert response.status_code == 201
    return response.json()


async def test_create_then_list_then_get_then_pdf_then_void():
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
        assert bill["claim_count"] == 2
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
        assert bill["id"] not in [b["id"] for b in client.get("/bills").json()]
        assert client.delete(f"/bills/{bill['id']}").status_code == 404
        claims_after_delete = client.get("/claims", params={"status": "brouillon"}).json()
        assert {claim_a["id"], claim_b["id"]} <= {c["id"] for c in claims_after_delete}

        # Released claims can go on a new bill.
        rebilled = client.post(
            "/bills",
            json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": [claim_a["id"]]},
        )
        assert rebilled.status_code == 201

    # A void, not a hard delete: the invoice number and its totals stay on record.
    async with session_scope() as session:
        stored = await session.get(Bill, bill["id"])
    assert stored is not None
    assert stored.voided_at is not None
    assert stored.claim_count == 2


async def _seed_claim_with_fee(client, *, patient_id, service_date, fee_amount):
    result = {
        "codes": [
            {
                "code": "TEST-BP-MGMT",
                "description": "Prise en charge d'une hypertension",
                "confidence": "high",
                "explanation": "hypertension artérielle depuis 10 ans",
                "fees": [{"amount": fee_amount, "amount_text": None, "context": "Par visite de suivi", "lieux": [], "majoration": None}],
            }
        ],
        "notes": None,
    }
    return await _seed_claim(client, patient_id=patient_id, service_date=service_date, result=result)


async def test_create_bill_total_is_exact_not_binary_float_drift():
    # 0.1 + 0.2 == 0.30000000000000004 in binary float — the bill total must be
    # computed in Decimal (see app/bills/service.py's `total` accumulator) so this
    # sums to exactly 0.30 rather than drifting by a fraction of a cent.
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim_a = await _seed_claim_with_fee(
            client, patient_id=patient.id, service_date="2026-02-10", fee_amount=0.10
        )
        claim_b = await _seed_claim_with_fee(
            client, patient_id=patient.id, service_date="2026-02-15", fee_amount=0.20
        )

        create_response = client.post(
            "/bills",
            json={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "claim_ids": [claim_a["id"], claim_b["id"]],
            },
        )
        assert create_response.status_code == 201
        assert create_response.json()["total_amount"] == 0.30


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
