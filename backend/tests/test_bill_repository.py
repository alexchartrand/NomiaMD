"""Exercises BillRepository directly against the test DB — no HTTP. The full API-level
behavior (validation, PDF, ownership scoping) is covered by tests/test_bills.py."""

import itertools
from datetime import date

import pytest

from app.postgresdb import (
    BillInput,
    BillRepository,
    ClaimCodeInput,
    ClaimInput,
    ClaimRepository,
    Gender,
    PatientRepository,
    init_db,
)

_physician_ids = itertools.count(3000)


@pytest.fixture(autouse=True)
async def _init_db():
    await init_db()


@pytest.fixture
def physician_id():
    return next(_physician_ids)


async def _seed_patient(physician_id):
    return await PatientRepository().create(
        physician_id=physician_id,
        full_name="Roch Desjardins",
        ramq_number="DESR81021001",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_registered_with_physician=True,
        is_vulnerable=False,
    )


async def _seed_claim(physician_id, patient_id, *, status="brouillon", service_date=date(2026, 2, 10)):
    created = await ClaimRepository().create(
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
                    confidence=0.9,
                    explanation="hypertension artérielle depuis 10 ans",
                    fee_amount=33.15,
                    fee_when_to_use="Par visite de suivi",
                    majoration=None,
                )
            ],
        )
    )
    return created.record


async def test_create_flips_claims_to_soumis_in_one_transaction(physician_id):
    patient = await _seed_patient(physician_id)
    claim_a = await _seed_claim(physician_id, patient.id)
    claim_b = await _seed_claim(physician_id, patient.id, service_date=date(2026, 2, 15))

    repo = BillRepository()
    bill = await repo.create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            claim_ids=[claim_a.id, claim_b.id],
            total_amount=66.30,
        )
    )

    assert bill is not None
    assert bill.record_count == 2
    assert set(await repo.claim_ids_for_bill(bill.id)) == {claim_a.id, claim_b.id}

    claim_repo = ClaimRepository()
    refreshed_a = await claim_repo.get_for_physician(claim_a.id, physician_id)
    refreshed_b = await claim_repo.get_for_physician(claim_b.id, physician_id)
    assert refreshed_a.record.status == "soumis"
    assert refreshed_b.record.status == "soumis"


async def test_create_rejects_a_non_brouillon_claim_and_writes_nothing(physician_id):
    patient = await _seed_patient(physician_id)
    claim = await _seed_claim(physician_id, patient.id, status="soumis")

    repo = BillRepository()
    bill = await repo.create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            claim_ids=[claim.id],
            total_amount=33.15,
        )
    )

    assert bill is None
    assert await repo.list_for_physician(physician_id) == []


async def test_create_rejects_another_physicians_claim(physician_id):
    other_physician_id = physician_id + 1
    other_patient = await _seed_patient(other_physician_id)
    foreign_claim = await _seed_claim(other_physician_id, other_patient.id)

    repo = BillRepository()
    bill = await repo.create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            claim_ids=[foreign_claim.id],
            total_amount=33.15,
        )
    )

    assert bill is None


async def test_delete_releases_claims_to_brouillon(physician_id):
    patient = await _seed_patient(physician_id)
    claim = await _seed_claim(physician_id, patient.id)

    repo = BillRepository()
    bill = await repo.create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            claim_ids=[claim.id],
            total_amount=33.15,
        )
    )
    assert bill is not None

    deleted = await repo.delete_for_physician(bill.id, physician_id)
    assert deleted is True
    assert await repo.get_for_physician(bill.id, physician_id) is None

    claim_repo = ClaimRepository()
    refreshed = await claim_repo.get_for_physician(claim.id, physician_id)
    assert refreshed.record.status == "brouillon"


async def test_cross_physician_access_returns_none_or_false(physician_id):
    patient = await _seed_patient(physician_id)
    claim = await _seed_claim(physician_id, patient.id)

    repo = BillRepository()
    bill = await repo.create(
        BillInput(
            physician_id=physician_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            claim_ids=[claim.id],
            total_amount=33.15,
        )
    )
    assert bill is not None
    other_physician_id = physician_id + 1

    assert await repo.get_for_physician(bill.id, other_physician_id) is None
    assert await repo.delete_for_physician(bill.id, other_physician_id) is False
