"""Exercises BillRepository directly against the test DB — no HTTP. The full API-level
behavior (validation, PDF, ownership scoping) is covered by tests/test_bills.py."""

import itertools
from datetime import date
from decimal import Decimal

import pytest

from app.postgresdb import (
    BillInput,
    BillRepository,
    ClaimAlreadyBilledError,
    ClaimCodeInput,
    ClaimInput,
    ClaimRepository,
    Gender,
    PatientRepository,
)
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(3000)
# Patients are globally unique by NAM now, so each seeded patient still needs its own NAM
# regardless of which physician_id it's seeded under.
_ramq_numbers = itertools.count(1)


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


async def _seed_patient(session):
    # "BLRP" prefix (not "DESR") to stay distinct from test_claims.py's/
    # test_claim_repository.py's own counters — patients are globally unique by NAM now,
    # and the test DB is shared across the whole session (see conftest.py).
    return await PatientRepository(session).create(
        full_name="Roch Desjardins",
        ramq_number=f"BLRP{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


async def _seed_claim(session, physician_id, patient_id, *, status="brouillon", service_date=date(2026, 2, 10)):
    created = await ClaimRepository(session).create(
        ClaimInput(
            physician_id=physician_id,
            patient_id=patient_id,
            service_date=service_date,
            status=status,
            source_system=None,
            summary_extraction_record_id=None,
            billing_extraction_record_id=None,
            codes=[
                ClaimCodeInput(
                    code="TEST-BP-MGMT",
                    description="Prise en charge d'une hypertension",
                    confidence="high",
                    explanation="hypertension artérielle depuis 10 ans",
                    fee_amount=Decimal("33.15"),
                    fee_when_to_use="Par visite de suivi",
                    majoration=None,
                )
            ],
        )
    )
    return created.record


def _bill_input(physician_id, claim_ids, total="33.15"):
    return BillInput(
        physician_id=physician_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        claim_ids=claim_ids,
        total_amount=Decimal(total),
    )


async def test_create_links_every_requested_claim(db_session, physician_id):
    patient = await _seed_patient(db_session)
    claim_a = await _seed_claim(db_session, physician_id, patient.id)
    claim_b = await _seed_claim(db_session, physician_id, patient.id, service_date=date(2026, 2, 15))

    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id, [claim_a.id, claim_b.id], total="66.30"))

    assert bill.record_count == 2
    assert bill.total_amount == Decimal("66.30")
    assert set(await repo.claim_ids_for_bill(bill.id)) == {claim_a.id, claim_b.id}


async def test_linking_a_claim_already_on_another_bill_is_rejected(db_session, physician_id):
    # bill_claims' unique claim_id is the backstop for two bills racing over the same claim;
    # which claims may be billed at all is BillService's (and ClaimLifecycle's) call.
    patient = await _seed_patient(db_session)
    claim = await _seed_claim(db_session, physician_id, patient.id)
    repo = BillRepository(db_session)
    await repo.create(_bill_input(physician_id, [claim.id]))

    with pytest.raises(ClaimAlreadyBilledError):
        await repo.create(_bill_input(physician_id, [claim.id]))


async def test_delete_removes_the_bill_and_its_links(db_session, physician_id):
    patient = await _seed_patient(db_session)
    claim = await _seed_claim(db_session, physician_id, patient.id)
    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id, [claim.id]))

    await repo.delete(bill)

    assert await repo.get_for_physician(bill.id, physician_id) is None
    assert await repo.claim_ids_for_bill(bill.id) == []


async def test_cross_physician_get_returns_none(db_session, physician_id):
    patient = await _seed_patient(db_session)
    claim = await _seed_claim(db_session, physician_id, patient.id)
    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id, [claim.id]))

    assert await repo.get_for_physician(bill.id, physician_id + 1) is None


async def test_claim_set_status_stores_the_given_status(db_session, physician_id):
    patient = await _seed_patient(db_session)
    claim = await _seed_claim(db_session, physician_id, patient.id)
    claims = ClaimRepository(db_session)

    await claims.set_status([claim.id], "soumis")

    refreshed = await claims.get_for_physician(claim.id, physician_id)
    assert refreshed.record.status == "soumis"
