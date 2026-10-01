"""Exercises BillRepository directly against the test DB — no HTTP. Attaching claims to a
bill is ClaimRepository's (tests/test_claim_repository.py); the full API-level behavior
(validation, PDF, ownership scoping) is covered by tests/test_bills.py."""

import itertools
from datetime import date
from decimal import Decimal

import pytest

from app.postgresdb import BillInput, BillRepository
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(3000)


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


def _bill_input(physician_id, *, start_date=date(2026, 2, 1)):
    return BillInput(
        physician_id=physician_id,
        start_date=start_date,
        end_date=date(2026, 2, 28),
        claim_count=2,
        total_amount=Decimal("66.30"),
    )


async def test_create_then_get(db_session, physician_id):
    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id))

    assert bill.generated_at is not None
    assert (bill.claim_count, bill.total_amount) == (2, Decimal("66.30"))
    assert await repo.get_for_physician(bill.id, physician_id) is bill


async def test_void_hides_the_bill_but_keeps_the_row(db_session, physician_id):
    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id))

    await repo.void(bill)

    assert bill.voided_at is not None
    assert await repo.get_for_physician(bill.id, physician_id) is None
    assert await repo.list_for_physician(physician_id) == []


async def test_list_orders_newest_first(db_session, physician_id):
    # generated_at is stamped by the DB clock (second precision on SQLite), so id breaks
    # the tie between two bills generated in the same second.
    repo = BillRepository(db_session)
    first = await repo.create(_bill_input(physician_id))
    second = await repo.create(_bill_input(physician_id))

    assert [b.id for b in await repo.list_for_physician(physician_id)] == [second.id, first.id]


async def test_cross_physician_get_returns_none(db_session, physician_id):
    repo = BillRepository(db_session)
    bill = await repo.create(_bill_input(physician_id))

    assert await repo.get_for_physician(bill.id, physician_id + 1) is None
