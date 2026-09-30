"""Exercises ClaimRepository directly against the test DB — no HTTP. The full
API-level behavior (validation, hydration from an extraction record, duplicate handling)
is covered by tests/test_claims.py once the claims router exists."""

import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.postgresdb import (
    ClaimCodeInput,
    ClaimInput,
    ClaimRepository,
    ExtractionRecord,
    ExtractionRecordInput,
    ExtractionRepository,
    Gender,
    PatientRepository,
    init_db,
)
from app.postgresdb.database import async_session
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(2000)
# Patients are globally unique by NAM now, so each seeded patient still needs its own NAM
# even though every test here used to reuse the same literal NAM under a distinct
# physician_id.
_ramq_numbers = itertools.count(1)


@pytest.fixture(autouse=True)
async def _init_db():
    await init_db()


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


async def _seed_patient():
    # "CLRP" prefix (not "DESR") to stay distinct from test_claims.py's/
    # test_bill_repository.py's own counters — patients are globally unique by NAM now, and
    # the test DB is shared across the whole session (see conftest.py).
    return await PatientRepository().create(
        full_name="Roch Desjardins",
        ramq_number=f"CLRP{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


def _one_code_input(**overrides):
    defaults = dict(
        code="TEST-BP-MGMT",
        description="Prise en charge d'une hypertension",
        confidence="high",
        explanation="hypertension artérielle depuis 10 ans",
        fee_amount=Decimal("33.15"),
        fee_when_to_use="Par visite de suivi",
        majoration=None,
    )
    defaults.update(overrides)
    return ClaimCodeInput(**defaults)


async def test_create_then_get_then_list(physician_id):
    patient = await _seed_patient()
    repo = ClaimRepository()

    created = await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 2, 10),
            status="brouillon",
            source_system="simule",
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input(), _one_code_input(code="TEST-BLOODWORK-ORDER", fee_amount=None)],
        )
    )
    assert created.record.id is not None
    assert len(created.codes) == 2

    fetched = await repo.get_for_physician(created.record.id, physician_id)
    assert fetched is not None
    assert fetched.patient_full_name == "Roch Desjardins"
    assert {c.code for c in fetched.codes} == {"TEST-BP-MGMT", "TEST-BLOODWORK-ORDER"}

    listed = await repo.list_for_physician(physician_id)
    assert [r.record.id for r in listed] == [created.record.id]
    assert listed[0].patient_full_name == "Roch Desjardins"


async def test_list_filters_and_ordering(physician_id):
    patient = await _seed_patient()
    repo = ClaimRepository()
    older = await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 1, 1),
            status="brouillon",
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input()],
        )
    )
    newer = await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 3, 1),
            status="facture",
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input()],
        )
    )

    all_records = await repo.list_for_physician(physician_id)
    assert [r.record.id for r in all_records] == [newer.record.id, older.record.id]

    only_facture = await repo.list_for_physician(physician_id, status="facture")
    assert [r.record.id for r in only_facture] == [newer.record.id]

    date_ranged = await repo.list_for_physician(physician_id, date_from=date(2026, 2, 1))
    assert [r.record.id for r in date_ranged] == [newer.record.id]


async def test_delete(physician_id):
    patient = await _seed_patient()
    repo = ClaimRepository()
    created = await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 2, 10),
            status="brouillon",
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input()],
        )
    )

    deleted = await repo.delete_for_physician(created.record.id, physician_id)
    assert deleted is True
    assert await repo.get_for_physician(created.record.id, physician_id) is None
    assert await repo.list_for_physician(physician_id) == []


async def test_cross_physician_access_returns_none_or_false(physician_id):
    patient = await _seed_patient()
    repo = ClaimRepository()
    created = await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 2, 10),
            status="brouillon",
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input()],
        )
    )
    other_physician_id = physician_id + 1

    assert await repo.get_for_physician(created.record.id, other_physician_id) is None
    assert await repo.delete_for_physician(created.record.id, other_physician_id) is False


async def test_count_for_patient_on_date(physician_id):
    patient = await _seed_patient()
    repo = ClaimRepository()

    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 10)) == 0

    await repo.create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient.id,
            service_date=date(2026, 2, 10),
            status="brouillon",
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[_one_code_input()],
        )
    )

    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 10)) == 1
    assert await repo.count_for_patient_on_date(physician_id, patient.id, date(2026, 2, 11)) == 0


def _claim_input(physician_id, patient_id, *, billing_extraction_record_id=None):
    return ClaimInput(
        physician_id=physician_id,
        patient_id=patient_id,
        service_date=date(2026, 2, 10),
        status="brouillon",
        source_system=None,
        summary_extraction_record_id=None,
        billing_extraction_record_id=billing_extraction_record_id,
        codes=[_one_code_input()],
    )


async def test_claim_for_an_unknown_physician_is_rejected():
    # Guards the SQLite foreign_keys pragma (app/postgresdb/database.py): without it, this
    # dangling physician_id would be accepted silently in dev and tests.
    patient = await _seed_patient()

    with pytest.raises(IntegrityError):
        await ClaimRepository().create(_claim_input(999_999, patient.id))


async def test_purging_the_source_extraction_keeps_the_claim(physician_id):
    patient = await _seed_patient()
    [extraction] = await ExtractionRepository().create_many(
        [
            ExtractionRecordInput(
                task="billing_codes",
                transcript="transcript de test",
                result={"codes": []},
                model="mistral-small-latest",
                source_system=None,
                user_id=physician_id,
            )
        ]
    )
    repo = ClaimRepository()
    created = await repo.create(
        _claim_input(physician_id, patient.id, billing_extraction_record_id=extraction.id)
    )

    async with async_session() as session:
        await session.execute(delete(ExtractionRecord).where(ExtractionRecord.id == extraction.id))
        await session.commit()

    detail = await repo.get_for_physician(created.record.id, physician_id)
    assert detail is not None
    assert detail.record.billing_extraction_record_id is None
    assert [c.code for c in detail.codes] == ["TEST-BP-MGMT"]
