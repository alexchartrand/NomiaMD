"""Unit tests for ClaimContextSnapshotter (app/claims/context.py), isolated from the real
BillingContextBuilder via a small fake."""

from datetime import date

from app.claims.context import ClaimContextSnapshotter
from app.postgresdb import User, UserRole
from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext


class _FakeContextBuilder:
    def __init__(self, context: BillingContext):
        self._context = context

    async def build(self, *, user: User, patient_id: int, encounter_date: date | None) -> BillingContext:
        return self._context


def _user() -> User:
    return User(id=1, email="doc@example.test", hashed_password="x", full_name="Dr. Doe", role=UserRole.PHYSICIAN)


async def _snapshot(physician: PhysicianContext):
    context = BillingContext(physician=physician, patient=PatientContext(age_years=58.7))
    snapshotter = ClaimContextSnapshotter(_FakeContextBuilder(context))
    return await snapshotter.snapshot(physician=_user(), patient_id=2, service_date=date(2026, 6, 1))


async def test_snapshots_a_panel_size_in_effect_on_the_service_date():
    snapshot = await _snapshot(PhysicianContext(panel_size=320))

    assert snapshot.record.panel_size == 320
    assert snapshot.record.patient_age_years == 58


async def test_never_records_an_assumed_panel_size_as_fact():
    snapshot = await _snapshot(PhysicianContext(panel_size=320, is_assumed=True))

    assert snapshot.record.panel_size is None


async def test_hand_picked_codes_are_checked_against_the_same_context():
    snapshot = await _snapshot(PhysicianContext(panel_size=320))

    assert snapshot.eligibility.panel_size == 320
    assert snapshot.eligibility.age == 58


async def test_an_assumed_panel_size_never_filters_hand_picked_codes():
    snapshot = await _snapshot(PhysicianContext(panel_size=320, is_assumed=True))

    assert snapshot.eligibility.panel_size is None
