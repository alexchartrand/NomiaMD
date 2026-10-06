"""Exercises claims billed without an encounter (POST/PUT /claims/manual): every code comes
from the codes table (tests/fixtures/reference_data_test.json via conftest's
StubCodeRepository), eligibility-checked against the patient, with no same-day duplicate
guard — see app/claims/manual.py."""

import itertools
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.postgresdb import Claim, ExtractionStageInput, Gender, PatientRepository, session_scope
from tests.db_helpers import seed_run

_ramq_numbers = itertools.count(1)


async def _seed_patient(*, date_of_birth=date(1981, 2, 10)):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name="Manon Tremblay",
            ramq_number=f"TREM{next(_ramq_numbers):08d}",
            date_of_birth=date_of_birth,
            gender=Gender.FEMALE,
            is_vulnerable=False,
        )


def _payload(patient_id, *codes, service_date="2026-03-02"):
    return {
        "patient_id": patient_id,
        "service_date": service_date,
        "selected_codes": [{"code": code, "fee_index": 0} for code in codes or ("00059",)],
    }


def _live_claim_ids(client, patient_id):
    return [c["id"] for c in client.get("/claims", params={"patient_id": patient_id}).json()]


async def test_create_bills_hand_picked_codes_with_no_encounter():
    with TestClient(app) as client:
        patient = await _seed_patient()

        response = client.post("/claims/manual", json=_payload(patient.id, "00059", "15801"))

        assert response.status_code == 201
        claim = response.json()
        assert claim["patient_id"] == patient.id
        assert claim["source_system"] == "manual"
        assert claim["status"] == "brouillon"
        assert [(c["code"], c["origin"]) for c in claim["codes"]] == [("00059", "manual"), ("15801", "manual")]
        assert claim["total_amount"] == 25.0 + 52.4
        assert claim["id"] in _live_claim_ids(client, patient.id)
    async with session_scope() as session:
        stored = await session.get(Claim, claim["id"])
    assert stored.extraction_run_id is None
    assert stored.patient_age_years == 45


async def test_the_chosen_fee_and_lieu_are_snapshotted():
    with TestClient(app) as client:
        patient = await _seed_patient()
        payload = _payload(patient.id)
        payload["selected_codes"] = [{"code": "15801", "fee_index": 1, "lieu": "domicile"}]

        response = client.post("/claims/manual", json=payload)

    assert response.status_code == 201
    [line] = response.json()["codes"]
    assert (line["fee_amount"], line["fee_context"], line["fee_lieux"]) == (61.1, "À domicile", ["domicile"])


async def test_a_code_the_patient_is_ineligible_for_is_refused():
    with TestClient(app) as client:
        patient = await _seed_patient()

        response = client.post("/claims/manual", json=_payload(patient.id, "00059", "09090"))

        assert response.status_code == 422
        assert "09090" in response.json()["detail"]
        assert _live_claim_ids(client, patient.id) == []


async def test_a_child_may_be_billed_a_pediatric_code():
    with TestClient(app) as client:
        patient = await _seed_patient(date_of_birth=date(2020, 5, 1))

        response = client.post("/claims/manual", json=_payload(patient.id, "09090"))

    assert response.status_code == 201


async def test_an_unknown_code_is_refused():
    with TestClient(app) as client:
        patient = await _seed_patient()

        response = client.post("/claims/manual", json=_payload(patient.id, "99999"))

    assert response.status_code == 422


async def test_an_unknown_patient_is_404():
    with TestClient(app) as client:
        response = client.post("/claims/manual", json=_payload(999999))

    assert response.status_code == 404


async def test_an_empty_selection_is_422():
    with TestClient(app) as client:
        patient = await _seed_patient()
        payload = _payload(patient.id)
        payload["selected_codes"] = []

        response = client.post("/claims/manual", json=payload)

    assert response.status_code == 422


async def test_no_same_day_duplicate_guard():
    with TestClient(app) as client:
        patient = await _seed_patient()

        first = client.post("/claims/manual", json=_payload(patient.id))
        second = client.post("/claims/manual", json=_payload(patient.id))

    assert (first.status_code, second.status_code) == (201, 201)


async def test_replace_voids_the_draft_and_saves_the_new_selection():
    with TestClient(app) as client:
        patient = await _seed_patient()
        first = client.post("/claims/manual", json=_payload(patient.id)).json()

        response = client.put(
            f"/claims/manual/{first['id']}", json=_payload(patient.id, "15802", service_date="2026-03-03")
        )

        assert response.status_code == 200
        replaced = response.json()
        assert [c["code"] for c in replaced["codes"]] == ["15802"]
        assert replaced["service_date"] == "2026-03-03"
        assert _live_claim_ids(client, patient.id) == [replaced["id"]]


async def test_a_refused_replacement_leaves_the_draft_live():
    with TestClient(app) as client:
        patient = await _seed_patient()
        first = client.post("/claims/manual", json=_payload(patient.id)).json()

        response = client.put(f"/claims/manual/{first['id']}", json=_payload(patient.id, "09090"))

        assert response.status_code == 422
        assert _live_claim_ids(client, patient.id) == [first["id"]]


async def test_an_encounters_claim_cannot_be_replaced_as_a_manual_one_nor_the_reverse():
    with TestClient(app) as client:
        patient = await _seed_patient()
        async with session_scope() as session:
            run = await seed_run(
                session,
                user_id=1,
                patient_id=patient.id,
                stages=[
                    ExtractionStageInput(
                        task="billing_codes",
                        model="mistral-small-latest",
                        result={"codes": [{"code": "00059", "description": "Suture", "confidence": "high", "explanation": ""}]},
                    )
                ],
            )
        encounter_claim = client.post(
            "/claims",
            json={"extraction_run_id": run.id, "service_date": "2026-03-02", "selected_codes": [{"code": "00059"}]},
        ).json()
        manual_claim = client.post("/claims/manual", json=_payload(patient.id)).json()

        as_manual = client.put(f"/claims/manual/{encounter_claim['id']}", json=_payload(patient.id))
        as_encounter = client.put(
            f"/claims/{manual_claim['id']}",
            json={"extraction_run_id": run.id, "service_date": "2026-03-02", "selected_codes": [{"code": "00059"}]},
        )

        assert (as_manual.status_code, as_encounter.status_code) == (422, 422)
        assert set(_live_claim_ids(client, patient.id)) == {encounter_claim["id"], manual_claim["id"]}


async def test_replacing_a_billed_manual_claim_is_409():
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim = client.post("/claims/manual", json=_payload(patient.id)).json()
        client.post("/bills", json={"start_date": "2026-03-01", "end_date": "2026-03-31", "claim_ids": [claim["id"]]})

        response = client.put(f"/claims/manual/{claim['id']}", json=_payload(patient.id))

    assert response.status_code == 409


async def test_a_manual_claim_goes_on_a_bill_and_its_pdf_renders():
    with TestClient(app) as client:
        patient = await _seed_patient()
        claim = client.post("/claims/manual", json=_payload(patient.id)).json()

        bill = client.post(
            "/bills", json={"start_date": "2026-03-01", "end_date": "2026-03-31", "claim_ids": [claim["id"]]}
        )
        assert bill.status_code == 201
        pdf = client.get(f"/bills/{bill.json()['id']}/pdf")

    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")
