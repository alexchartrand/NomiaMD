"""Exercises ClaimRepository directly against the test DB — no HTTP. The full
API-level behavior (validation, hydration from an extraction run, duplicate handling)
is covered by tests/test_claims.py."""

import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.postgresdb import (
    BillInput,
    BillRepository,
    ClaimAlreadyBilledError,
    ClaimCodeInput,
    ClaimContextInput,
    ClaimInput,
    ClaimRepository,
    ExtractionAlreadyClaimedError,
    ExtractionRun,
    ExtractionStageInput,
    Gender,
    PatientRepository,
)
from tests.db_helpers import ensure_user_row, physician, seed_run

_physician_ids = itertools.count(2000)
# Patients are globally unique by NAM, so each seeded patient needs its own NAM.
_ramq_numbers = itertools.count(1)


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


async def _seed_patient(session):
    # "CLRP" prefix (not "DESR") to stay distinct from test_claims.py's/
    # test_bill_repository.py's own counters — the test DB is shared across the whole
    # session (see conftest.py).
    return await PatientRepository(session).create(
        full_name="Roch Desjardins",
        ramq_number=f"CLRP{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


async def _seed_run(session, physician_id, patient_id) -> ExtractionRun:
    return await seed_run(
        session,
        user_id=physician_id,
        patient_id=patient_id,
        source_system=None,
        stages=[ExtractionStageInput(task="billing_codes", model="mistral-small-latest", result={"codes": []})],
    )


def _one_code_input(**overrides):
    defaults = dict(
        code="TEST-BP-MGMT",
        description="Prise en charge d'une hypertension",
        confidence="high",
        explanation="hypertension artérielle depuis 10 ans",
        fee_amount=Decimal("33.15"),
        fee_unit="dollars",
        fee_units=None,
        fee_role=1,
        fee_context="Par visite de suivi",
        fee_lieux=["cabinet"],
        majoration=None,
        manual_rev=None,
    )
    defaults.update(overrides)
    return ClaimCodeInput(**defaults)


_UNKNOWN_CONTEXT = ClaimContextInput(is_registered=None, is_vulnerable=None, patient_age_years=None, panel_size=None)


async def _claim_input(session, physician_id, patient_id, *, service_date=date(2026, 2, 10), run_id=None, codes=None):
    if run_id is None:
        run_id = (await _seed_run(session, physician_id, patient_id)).id
    return ClaimInput(
        physician_id=physician_id,
        patient_id=patient_id,
        service_date=service_date,
        source_system=None,
        source_note_hash=None,
        external_note_id=None,
        extraction_run_id=run_id,
        context=_UNKNOWN_CONTEXT,
        codes=codes or [_one_code_input()],
    )


async def _bill(session, physician_id):
    return await BillRepository(session).create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            claim_count=1,
            total_amount=None,
        )
    )


async def test_create_then_get_then_list(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)

    created = await repo.create(
        await _claim_input(
            db_session,
            physician_id,
            patient.id,
            codes=[_one_code_input(), _one_code_input(code="TEST-BLOODWORK-ORDER", fee_amount=None)],
        )
    )
    assert created.claim.id is not None
    assert created.claim.created_at is not None
    assert len(created.codes) == 2

    assert await repo.get_for_physician(created.claim.id, physician_id) is created.claim

    listed = await repo.list_for_physician(physician_id)
    assert [r.claim.id for r in listed] == [created.claim.id]
    assert listed[0].patient_full_name == "Roch Desjardins"
    assert {c.code for c in listed[0].codes} == {"TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"}
    first = next(c for c in listed[0].codes if c.code == "TEST-BP-MGMT")
    assert (first.fee_unit, first.fee_role, first.fee_context, first.fee_lieux) == (
        "dollars",
        1,
        "Par visite de suivi",
        ["cabinet"],
    )


async def test_create_snapshots_the_billing_context(db_session, physician_id):
    patient = await _seed_patient(db_session)
    data = await _claim_input(db_session, physician_id, patient.id)
    data.context = ClaimContextInput(is_registered=True, is_vulnerable=False, patient_age_years=45, panel_size=320)

    created = await ClaimRepository(db_session).create(data)

    claim = created.claim
    assert (claim.is_registered, claim.is_vulnerable, claim.patient_age_years, claim.panel_size) == (
        True,
        False,
        45,
        320,
    )


async def test_list_filters_and_ordering(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    older = await repo.create(await _claim_input(db_session, physician_id, patient.id, service_date=date(2026, 1, 1)))
    newer = await repo.create(await _claim_input(db_session, physician_id, patient.id, service_date=date(2026, 3, 1)))
    bill = await _bill(db_session, physician_id)
    await repo.attach_to_bill([newer.claim.id], bill.id)

    all_records = await repo.list_for_physician(physician_id)
    assert [r.claim.id for r in all_records] == [newer.claim.id, older.claim.id]

    assert [r.claim.id for r in await repo.list_for_physician(physician_id, billed=True)] == [newer.claim.id]
    assert [r.claim.id for r in await repo.list_for_physician(physician_id, billed=False)] == [older.claim.id]

    date_ranged = await repo.list_for_physician(physician_id, date_from=date(2026, 2, 1))
    assert [r.claim.id for r in date_ranged] == [newer.claim.id]


async def test_same_day_claims_order_newest_first(db_session, physician_id):
    # created_at is stamped by the DB clock (second precision on SQLite), so two claims saved
    # in the same second must still come back in a stable order.
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    first = await repo.create(await _claim_input(db_session, physician_id, patient.id))
    second = await repo.create(await _claim_input(db_session, physician_id, patient.id))

    listed = await repo.list_for_physician(physician_id)

    assert [r.claim.id for r in listed] == [second.claim.id, first.claim.id]


async def test_void_hides_the_claim_but_keeps_the_row(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    created = await repo.create(await _claim_input(db_session, physician_id, patient.id))

    await repo.void(created.claim)

    assert created.claim.voided_at is not None
    assert await repo.get_for_physician(created.claim.id, physician_id) is None
    assert await repo.list_for_physician(physician_id) == []
    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 10)) == 0


async def test_cross_physician_access_returns_none(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    created = await repo.create(await _claim_input(db_session, physician_id, patient.id))

    assert await repo.get_for_physician(created.claim.id, physician_id + 1) is None


async def test_count_for_patient_on_date(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)

    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 10)) == 0

    await repo.create(await _claim_input(db_session, physician_id, patient.id))

    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 10)) == 1
    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 11)) == 0


async def test_claim_for_an_unknown_physician_is_rejected(db_session, physician_id):
    # Guards the SQLite foreign_keys pragma (app/postgresdb/database.py): without it, this
    # dangling physician_id would be accepted silently in dev and tests.
    patient = await _seed_patient(db_session)
    data = await _claim_input(db_session, physician_id, patient.id)
    data.physician_id = 999_999

    with pytest.raises(IntegrityError):
        await ClaimRepository(db_session).create(data)


async def test_a_code_appears_once_per_claim(db_session, physician_id):
    patient = await _seed_patient(db_session)
    data = await _claim_input(db_session, physician_id, patient.id, codes=[_one_code_input(), _one_code_input()])

    with pytest.raises(IntegrityError):
        await ClaimRepository(db_session).create(data)


async def test_an_unknown_confidence_is_rejected(db_session, physician_id):
    patient = await _seed_patient(db_session)
    data = await _claim_input(db_session, physician_id, patient.id, codes=[_one_code_input(confidence="certain")])

    with pytest.raises(IntegrityError):
        await ClaimRepository(db_session).create(data)


async def test_purging_the_source_extraction_keeps_the_claim(db_session, physician_id):
    patient = await _seed_patient(db_session)
    run = await _seed_run(db_session, physician_id, patient.id)
    repo = ClaimRepository(db_session)
    created = await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))

    await db_session.execute(delete(ExtractionRun).where(ExtractionRun.id == run.id))
    # The DB applied SET NULL, not the ORM — reload the claim instead of reading the cached one.
    db_session.expunge_all()

    [detail] = await repo.list_by_ids(physician_id, [created.claim.id])
    assert detail.claim.extraction_run_id is None
    assert detail.encounter_id is None
    assert [c.code for c in detail.codes] == ["TEST-BP-MGMT"]


async def test_a_listed_claim_carries_its_runs_encounter(db_session, physician_id):
    patient = await _seed_patient(db_session)
    run = await _seed_run(db_session, physician_id, patient.id)
    repo = ClaimRepository(db_session)
    await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))

    [detail] = await repo.list_for_physician(physician_id)
    assert detail.encounter_id == run.encounter_id


async def test_list_by_ids_returns_only_the_physicians_own_claims_with_their_codes(db_session, physician_id):
    other_physician_id = physician_id + 1
    await ensure_user_row(physician(other_physician_id))
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    mine = await repo.create(await _claim_input(db_session, physician_id, patient.id))
    theirs = await repo.create(await _claim_input(db_session, other_physician_id, patient.id))

    details = await repo.list_by_ids(physician_id, [mine.claim.id, theirs.claim.id, 999_999])

    assert [d.claim.id for d in details] == [mine.claim.id]
    assert details[0].patient_full_name == "Roch Desjardins"
    assert [c.code for c in details[0].codes] == ["TEST-BP-MGMT"]


async def test_a_second_claim_on_the_same_run_is_rejected(db_session, physician_id):
    patient = await _seed_patient(db_session)
    run = await _seed_run(db_session, physician_id, patient.id)
    repo = ClaimRepository(db_session)
    await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))

    with pytest.raises(ExtractionAlreadyClaimedError):
        await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))


async def test_voiding_a_claim_frees_its_run(db_session, physician_id):
    patient = await _seed_patient(db_session)
    run = await _seed_run(db_session, physician_id, patient.id)
    repo = ClaimRepository(db_session)
    first = await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))
    await repo.void(first.claim)

    second = await repo.create(await _claim_input(db_session, physician_id, patient.id, run_id=run.id))

    assert await repo.get_live_by_extraction_run_id(run.id) is second.claim


async def test_attach_then_detach_from_bill(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    created = await repo.create(await _claim_input(db_session, physician_id, patient.id))
    bill = await _bill(db_session, physician_id)

    await repo.attach_to_bill([created.claim.id], bill.id)
    assert [d.claim.id for d in await repo.list_for_bill(bill.id, physician_id)] == [created.claim.id]
    assert created.claim.bill_id == bill.id

    await repo.detach_from_bill(bill.id)
    assert await repo.list_for_bill(bill.id, physician_id) == []
    assert created.claim.bill_id is None


async def test_attach_refuses_a_claim_already_on_another_bill(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = ClaimRepository(db_session)
    created = await repo.create(await _claim_input(db_session, physician_id, patient.id))
    first_bill = await _bill(db_session, physician_id)
    second_bill = await _bill(db_session, physician_id)
    await repo.attach_to_bill([created.claim.id], first_bill.id)

    with pytest.raises(ClaimAlreadyBilledError):
        await repo.attach_to_bill([created.claim.id], second_bill.id)
