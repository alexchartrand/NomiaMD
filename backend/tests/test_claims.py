"""Exercises the /claims API end-to-end: create -> list -> filter -> void, plus
ownership scoping and the validation/duplicate rules in app/claims/service.py. Status is
derived and read-only from this API — a claim only leaves "brouillon" via POST /bills, see
test_voiding_a_claim_on_a_bill_is_409 and tests/test_bills.py.
"""

import itertools
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.intake import content_hash
from app.main import app
from app.postgresdb import (
    Claim,
    ExtractionStageInput,
    Gender,
    Patient,
    PatientRepository,
    User,
    UserRole,
    session_scope,
)
from tests.conftest import StubCodeRepository
from tests.db_helpers import ensure_user_row, physician, seed_run

# The test DB is shared (session-scoped file, not reset per test — see conftest.py), and
# patients are globally unique by NAM — so each seeded patient needs its own NAM to avoid
# tripping ix_patients_ramq_number_active (models.py) against an earlier test's patient.
_ramq_numbers = itertools.count(1)

BILLING_RESULT = {
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une hypertension",
            "confidence": "high",
            "explanation": "hypertension artérielle depuis 10 ans",
            "fees": [{"amount": 33.15, "amount_text": "33,15", "context": "Par visite de suivi", "lieux": [], "majoration": None}],
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


async def _seed_patient(*, full_name="Roch Desjardins", is_vulnerable=False):
    async with session_scope() as session:
        return await PatientRepository(session).create(
            full_name=full_name,
            ramq_number=f"DESR{next(_ramq_numbers):08d}",
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=is_vulnerable,
        )


async def _seed_run(patient_id, *, user_id=1, result=None, task="billing_codes"):
    await ensure_user_row(physician(user_id))
    async with session_scope() as session:
        return await seed_run(
            session,
            user_id=user_id,
            patient_id=patient_id,
            source_system="simule",
            stages=[
                ExtractionStageInput(
                    task=task,
                    model="mistral-small-latest",
                    result=result if result is not None else BILLING_RESULT,
                )
            ],
        )


async def _seed_patient_and_run(**run_kwargs):
    patient = await _seed_patient()
    return patient, await _seed_run(patient.id, **run_kwargs)


def _valid_payload(*, extraction_run_id, service_date="2026-02-10"):
    return {
        "extraction_run_id": extraction_run_id,
        "service_date": service_date,
        "selected_codes": [{"code": "TEST-BP-MGMT", "fee_index": 0}],
    }


async def test_create_then_list_then_filter_then_void():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()

        create_response = client.post("/claims", json=_valid_payload(extraction_run_id=run.id))
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["patient_id"] == patient.id
        assert created["patient_full_name"] == "Roch Desjardins"
        assert created["status"] == "brouillon"
        assert created["bill_id"] is None
        assert created["source_system"] == "simule"
        assert created["encounter_id"] == run.encounter_id
        async with session_scope() as session:
            stored = await session.get(Claim, created["id"])
        assert stored.source_note_hash == content_hash("transcript de test")
        assert stored.external_note_id is None
        assert created["total_amount"] == 33.15
        assert [c["code"] for c in created["codes"]] == ["TEST-BP-MGMT"]

        list_response = client.get("/claims")
        assert list_response.status_code == 200
        assert any(r["id"] == created["id"] for r in list_response.json())

        filtered_by_patient = client.get("/claims", params={"patient_id": patient.id})
        assert [r["id"] for r in filtered_by_patient.json()] == [created["id"]]
        assert filtered_by_patient.json()[0]["encounter_id"] == run.encounter_id

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

    # A void, not a hard delete: the row and its codes stay on record.
    async with session_scope() as session:
        stored = await session.get(Claim, created["id"])
    assert stored is not None
    assert stored.voided_at is not None


async def test_the_claims_patient_is_the_one_the_extraction_ran_for():
    # The codes were eligibility-filtered for the run's patient; nothing in the request can
    # move them onto someone else.
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        someone_else = await _seed_patient(full_name="Madeleine Lefebvre")

        payload = _valid_payload(extraction_run_id=run.id)
        payload["patient_id"] = someone_else.id
        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    assert response.json()["patient_id"] == patient.id


async def test_create_snapshots_the_billing_context_at_save_time():
    with TestClient(app) as client:
        patient = await _seed_patient(is_vulnerable=True)
        run = await _seed_run(patient.id)

        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

    async with session_scope() as session:
        stored = await session.get(Claim, created["id"])
    # Born 1981-02-10, seen 2026-02-10: 45 completed years. The default physician has no
    # practice number or profile, so registration and panel size stay unknown, not False/0.
    assert stored.patient_age_years == 45
    assert stored.is_vulnerable is True
    assert stored.is_registered is None
    assert stored.panel_size is None


async def test_voiding_a_claim_on_a_bill_is_409():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

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
        [billed] = [r for r in claim_after_billing if r["id"] == created["id"]]
        assert billed["bill_id"] == bill_response.json()["id"]

        delete_response = client.delete(f"/claims/{created['id']}")
        assert delete_response.status_code == 409


async def test_cross_physician_access_is_404():
    other_physician = _other_physician()

    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

        app.dependency_overrides[get_current_user] = lambda: other_physician
        try:
            get_list = client.get("/claims")
            delete_response = client.delete(f"/claims/{created['id']}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    assert all(r["id"] != created["id"] for r in get_list.json())
    assert delete_response.status_code == 404


async def test_creating_a_claim_for_a_patient_not_on_the_billing_physicians_roster_succeeds():
    # Patients are a shared, global identity — claiming one doesn't require having added
    # them to "my patients list" first (see app/postgresdb/models.py's Patient).
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        response = client.post("/claims", json=_valid_payload(extraction_run_id=run.id))

    assert response.status_code == 201


async def test_creating_for_a_patient_deleted_since_the_extraction_is_404():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        async with session_scope() as session:
            (await session.get(Patient, patient.id)).deleted_at = datetime.now(timezone.utc)

        response = client.post("/claims", json=_valid_payload(extraction_run_id=run.id))

    assert response.status_code == 404


async def test_creating_against_an_unknown_run_is_404():
    with TestClient(app) as client:
        response = client.post("/claims", json=_valid_payload(extraction_run_id=999_999))

    assert response.status_code == 404


async def test_creating_against_another_physicians_run_is_404():
    with TestClient(app) as client:
        _, other_physicians_run = await _seed_patient_and_run(user_id=99)

        response = client.post("/claims", json=_valid_payload(extraction_run_id=other_physicians_run.id))

    assert response.status_code == 404


async def test_a_run_without_a_billing_codes_result_is_404():
    with TestClient(app) as client:
        _, summary_only_run = await _seed_patient_and_run(
            task="consultation_summary", result={"short_description": "not a billing_codes result"}
        )

        response = client.post("/claims", json=_valid_payload(extraction_run_id=summary_only_run.id))

    assert response.status_code == 404


async def test_empty_selected_codes_is_422():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = []
        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_a_code_neither_suggested_nor_in_the_codes_table_is_422():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "NOT-A-CANDIDATE", "fee_index": 0}]
        response = client.post("/claims", json=payload)

    assert response.status_code == 422
    assert "NOT-A-CANDIDATE" in response.json()["detail"]


async def test_a_code_added_by_hand_is_snapshotted_from_the_codes_table():
    # 00059 isn't in the run's result: the physician added it from the code search.
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"].append({"code": "00059", "fee_index": 0})
        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    suggested, added = response.json()["codes"]
    assert (suggested["code"], suggested["origin"], suggested["confidence"]) == ("TEST-BP-MGMT", "suggested", "high")
    assert added["code"] == "00059"
    assert added["origin"] == "manual"
    assert added["confidence"] is None
    assert added["explanation"] == ""
    assert added["description"] == "Suture d'une plaie simple"
    assert added["fee_amount"] == 25.0
    assert added["manual_rev"] == StubCodeRepository.REVISION
    assert response.json()["total_amount"] == 58.15


async def test_a_code_added_by_hand_that_the_patient_is_ineligible_for_is_422():
    # 09090 is for patients under 18; the seeded patient was born in 1981.
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"].append({"code": "09090"})
        response = client.post("/claims", json=payload)

    assert response.status_code == 422
    assert "09090" in response.json()["detail"]


async def test_get_returns_the_physicians_live_claim_only():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

        assert client.get(f"/claims/{created['id']}").json()["id"] == created["id"]

        client.delete(f"/claims/{created['id']}")
        assert client.get(f"/claims/{created['id']}").status_code == 404


async def test_selecting_a_fee_index_lands_that_variant_on_the_claim():
    with TestClient(app) as client:
        multi_fee_result = {
            "codes": [
                {
                    "code": "TEST-BP-MGMT",
                    "description": "Prise en charge d'une hypertension",
                    "confidence": "high",
                    "explanation": "hypertension artérielle depuis 10 ans",
                    "fees": [
                        {"amount": 33.15, "amount_text": "33,15", "context": "Jour", "lieux": ["cabinet"], "majoration": None},
                        {"amount": 40.0, "amount_text": "40,00", "role": 1, "context": "Soir",
                         "lieux": ["cabinet", "domicile"], "majoration": "20%"},
                    ],
                }
            ],
            "notes": None,
        }
        _, run = await _seed_patient_and_run(result=multi_fee_result)
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 1}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    [code] = response.json()["codes"]
    assert code["fee_amount"] == 40.0
    assert code["fee_unit"] == "dollars"
    assert code["fee_units"] is None
    assert code["fee_role"] == 1
    assert code["fee_context"] == "Soir"
    assert code["fee_lieux"] == ["cabinet", "domicile"]
    assert code["majoration"] == "20%"


_TWO_LIEUX_RESULT = {
    "codes": [
        {
            "code": "TEST-BP-MGMT",
            "description": "Prise en charge d'une hypertension",
            "confidence": "high",
            "explanation": "hypertension artérielle depuis 10 ans",
            "fees": [
                {"amount": 40.0, "amount_text": "40,00", "context": "Jour", "lieux": ["cabinet", "domicile"],
                 "majoration": None},
            ],
        }
    ],
    "notes": None,
}


async def test_selecting_a_lieu_keeps_only_that_lieu_on_the_claim():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run(result=_TWO_LIEUX_RESULT)
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 0, "lieu": "domicile"}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    [code] = response.json()["codes"]
    assert code["fee_lieux"] == ["domicile"]
    assert code["fee_amount"] == 40.0


async def test_a_lieu_the_fee_does_not_offer_is_422():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run(result=_TWO_LIEUX_RESULT)
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 0, "lieu": "urgence"}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_a_fee_in_units_is_never_billed_as_dollars():
    # An R = 2 column counts anesthesia base units: "17" must never become $17 on a claim.
    with TestClient(app) as client:
        unit_fee_result = {
            "codes": [
                {
                    "code": "TEST-BP-MGMT",
                    "description": "Acte avec rémunération de l'anesthésiste",
                    "confidence": "high",
                    "explanation": "acte réalisé",
                    "fees": [
                        {"amount": 1344.75, "amount_text": "1 344,75", "role": 1, "unit": "dollars",
                         "context": None, "lieux": [], "majoration": None},
                        {"amount": 17.0, "amount_text": "17", "role": 2, "unit": "unités",
                         "context": None, "lieux": [], "majoration": None},
                    ],
                }
            ],
            "notes": None,
        }
        _, run = await _seed_patient_and_run(result=unit_fee_result)
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 1}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 201
    body = response.json()
    [code] = body["codes"]
    assert code["fee_amount"] is None
    assert code["fee_unit"] == "unités"
    assert code["fee_units"] == 17.0
    assert code["fee_role"] == 2
    assert body["total_amount"] is None


async def test_out_of_range_fee_index_is_422():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BP-MGMT", "fee_index": 5}]

        response = client.post("/claims", json=payload)

    assert response.status_code == 422


async def test_second_save_of_same_run_is_409():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        payload = _valid_payload(extraction_run_id=run.id)

        first = client.post("/claims", json=payload)
        assert first.status_code == 201

        second = client.post("/claims", json=payload)

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_claim"


async def test_second_save_of_same_run_is_409_even_with_confirm_duplicate():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        payload = _valid_payload(extraction_run_id=run.id)

        client.post("/claims", json=payload)
        second = client.post("/claims", json=payload, params={"confirm_duplicate": "true"})

    assert second.status_code == 409


async def test_a_voided_claims_run_can_be_claimed_again():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        payload = _valid_payload(extraction_run_id=run.id)

        first = client.post("/claims", json=payload).json()
        client.delete(f"/claims/{first['id']}")
        second = client.post("/claims", json=payload)

    assert second.status_code == 201


async def test_same_patient_and_date_via_different_run_warns_then_allows_override():
    with TestClient(app) as client:
        patient = await _seed_patient()
        first_run = await _seed_run(patient.id)
        second_run = await _seed_run(patient.id)

        first = client.post("/claims", json=_valid_payload(extraction_run_id=first_run.id))
        assert first.status_code == 201

        blocked = client.post("/claims", json=_valid_payload(extraction_run_id=second_run.id))
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "duplicate_claim"

        overridden = client.post(
            "/claims",
            json=_valid_payload(extraction_run_id=second_run.id),
            params={"confirm_duplicate": "true"},
        )
        assert overridden.status_code == 201


async def test_total_is_null_when_no_fees():
    with TestClient(app) as client:
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
        _, run = await _seed_patient_and_run(result=no_fee_result)
        payload = _valid_payload(extraction_run_id=run.id)
        payload["selected_codes"] = [{"code": "TEST-BLOODWORK-ORDER", "fee_index": None}]

        created = client.post("/claims", json=payload).json()

    assert created["total_amount"] is None
    [code] = created["codes"]
    assert code["fee_unit"] is None


def test_list_limit_above_the_maximum_is_422_not_silently_capped():
    with TestClient(app) as client:
        response = client.get("/claims", params={"limit": 500})

    assert response.status_code == 422


async def test_same_run_racing_past_the_pre_check_is_409_not_500(monkeypatch):
    # Two saves of one run can both pass ClaimDuplicateGuard's read before either commits;
    # the partial unique index must then surface as the same 409 as the pre-check.
    async def _nothing_saved_yet(self, extraction_run_id):
        return None

    monkeypatch.setattr("app.postgresdb.ClaimRepository.get_live_by_extraction_run_id", _nothing_saved_yet)
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()
        payload = _valid_payload(extraction_run_id=run.id)

        first = client.post("/claims", json=payload)
        second = client.post("/claims?confirm_duplicate=true", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_claim"


# --- PUT /claims/{id}: a changed review of a draft ------------------------------------------


def _live_claim_ids(client: TestClient, patient: Patient) -> list[int]:
    return [claim["id"] for claim in client.get("/claims", params={"patient_id": patient.id}).json()]


async def test_replacing_a_draft_voids_it_and_saves_the_new_selection():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        first = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

        response = client.put(
            f"/claims/{first['id']}",
            json={
                "extraction_run_id": run.id,
                "service_date": "2026-02-11",
                "selected_codes": [{"code": "TEST-BP-MGMT"}, {"code": "TEST-BLOODWORK-ORDER"}],
            },
        )

        assert response.status_code == 200
        replaced = response.json()
        assert replaced["id"] != first["id"]
        assert [c["code"] for c in replaced["codes"]] == ["TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"]
        assert replaced["service_date"] == "2026-02-11"
        live = _live_claim_ids(client, patient)
        assert replaced["id"] in live
        assert first["id"] not in live
    async with session_scope() as session:
        assert (await session.get(Claim, first["id"])).voided_at is not None


async def test_a_refused_replacement_leaves_the_draft_live():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        first = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

        response = client.put(
            f"/claims/{first['id']}",
            json={"extraction_run_id": run.id, "service_date": "2026-02-10", "selected_codes": []},
        )

        assert response.status_code == 422
        assert first["id"] in _live_claim_ids(client, patient)


async def test_replacing_a_claim_on_a_bill_is_409():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()
        client.post(
            "/bills",
            json={"start_date": "2026-02-01", "end_date": "2026-02-28", "claim_ids": [created["id"]]},
        )

        response = client.put(f"/claims/{created['id']}", json=_valid_payload(extraction_run_id=run.id))

        assert response.status_code == 409
        assert created["id"] in _live_claim_ids(client, patient)


async def test_replacing_from_another_encounters_run_is_422():
    with TestClient(app) as client:
        patient, run = await _seed_patient_and_run()
        other_run = await _seed_run(patient.id)
        created = client.post("/claims", json=_valid_payload(extraction_run_id=run.id)).json()

        response = client.put(f"/claims/{created['id']}", json=_valid_payload(extraction_run_id=other_run.id))

        assert response.status_code == 422
        assert created["id"] in _live_claim_ids(client, patient)


async def test_replacing_an_unknown_claim_is_404():
    with TestClient(app) as client:
        _, run = await _seed_patient_and_run()

        response = client.put("/claims/999999", json=_valid_payload(extraction_run_id=run.id))

    assert response.status_code == 404
