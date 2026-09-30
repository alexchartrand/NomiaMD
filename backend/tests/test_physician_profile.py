"""Covers the property the users/physician_profiles split exists for: a claim or invoice
from the past must read the practice facts that were in effect then, not whatever the
physician's profile says today."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.auth import get_current_user
from app.auth.factory import get_profile_service
from app.auth.profile import PracticeFacts, ProfileService
from app.auth.security import PasswordHasher
from app.clock import ClinicClock
from app.main import app
from app.postgresdb import (
    DbSession,
    PhysicianProfile,
    PhysicianProfileRepository,
    PhysicianType,
    RemunerationType,
    UserRepository,
    UserRole,
    session_scope,
)

PASSWORD = "correct horse battery staple"


async def _create_user():
    async with session_scope() as session:
        return await UserRepository(session).create(
            email=f"doc-{uuid.uuid4().hex[:8]}@example.test",
            hashed_password=PasswordHasher().hash(PASSWORD),
            full_name="Dr. Doe",
            role=UserRole.PHYSICIAN,
        )


TODAY = date(2026, 3, 15)


class _FixedClock:
    def __init__(self, today: date) -> None:
        self._today = today

    def today(self) -> date:
        return self._today


def _profile_service(session, today: date = TODAY) -> ProfileService:
    return ProfileService(UserRepository(session), PhysicianProfileRepository(session), _FixedClock(today))


def _facts(*, panel_size=None, remuneration_type=None, physician_type=None) -> PracticeFacts:
    return PracticeFacts(
        physician_type=physician_type, panel_size=panel_size, remuneration_type=remuneration_type
    )


async def test_no_profile_yet_reads_as_none(db_session):
    user = await _create_user()

    account = await _profile_service(db_session).current(user)

    assert account.profile is None


async def test_past_date_reads_the_version_in_effect_then(db_session):
    user = await _create_user()
    profiles = _profile_service(db_session)
    last_year = TODAY - timedelta(days=365)

    await profiles.record_practice_facts(
        user.id,
        _facts(
            physician_type=PhysicianType.MED_FAM.value,
            panel_size=500,
            remuneration_type=RemunerationType.A_L_ACTE.value,
        ),
        effective_from=last_year,
    )
    await profiles.record_practice_facts(
        user.id,
        _facts(
            physician_type=PhysicianType.MED_FAM.value,
            panel_size=1200,
            remuneration_type=RemunerationType.MIXTE.value,
        ),
    )

    back_then = (await profiles.as_of(user, last_year + timedelta(days=30))).profile
    assert back_then is not None
    assert back_then.panel_size == 500
    assert back_then.remuneration_type == RemunerationType.A_L_ACTE.value

    today = (await profiles.current(user)).profile
    assert today is not None
    assert today.panel_size == 1200
    assert today.remuneration_type == RemunerationType.MIXTE.value


async def test_date_before_the_first_version_reads_as_none(db_session):
    user = await _create_user()
    profiles = _profile_service(db_session)
    await profiles.record_practice_facts(
        user.id, _facts(panel_size=500), effective_from=TODAY - timedelta(days=10)
    )

    assert (await profiles.as_of(user, TODAY - timedelta(days=30))).profile is None


async def test_same_day_edits_overwrite_instead_of_piling_up(db_session):
    user = await _create_user()
    profiles = _profile_service(db_session)

    first = await profiles.record_practice_facts(user.id, _facts(panel_size=100))
    second = await profiles.record_practice_facts(user.id, _facts(panel_size=200))

    assert first.id == second.id
    current = (await profiles.current(user)).profile
    assert current is not None
    assert current.panel_size == 200


async def test_one_version_per_day_is_enforced_by_the_database(db_session):
    user = await _create_user()
    db_session.add_all(
        PhysicianProfile(user_id=user.id, effective_from=TODAY, panel_size=size) for size in (100, 200)
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_new_version_takes_effect_on_the_clocks_today(db_session):
    user = await _create_user()

    profile = await _profile_service(db_session, today=TODAY).record_practice_facts(
        user.id, _facts(panel_size=100)
    )

    assert profile.effective_from == TODAY


async def test_profile_edit_does_not_rewrite_an_earlier_version():
    """The regression the split prevents: before it, this edit mutated the single row
    every past claim's eligibility would be judged against."""
    user = await _create_user()
    # The real route uses ClinicClock, so "yesterday" must be the clinic's yesterday too —
    # the host's date.today() is already tomorrow in the evening, Montréal time.
    yesterday = ClinicClock().today() - timedelta(days=1)

    async with session_scope() as session:
        await _profile_service(session, today=yesterday).record_practice_facts(
            user.id, _facts(remuneration_type=RemunerationType.A_L_ACTE.value)
        )

    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={
                "full_name": "Dr. Doe",
                "physician_type": None,
                "panel_size": None,
                "remuneration_type": RemunerationType.MIXTE.value,
            },
        )

    assert response.status_code == 200
    assert response.json()["remuneration_type"] == RemunerationType.MIXTE.value

    async with session_scope() as session:
        yesterdays = await PhysicianProfileRepository(session).get_effective_on(user.id, yesterday)
    assert yesterdays is not None
    assert yesterdays.remuneration_type == RemunerationType.A_L_ACTE.value


async def test_me_returns_nulls_for_a_physician_with_no_profile():
    user = await _create_user()

    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["physician_type"] is None
    assert body["panel_size"] is None
    assert body["remuneration_type"] is None


class _FailingProfileRepository(PhysicianProfileRepository):
    async def upsert(self, *args, **kwargs):
        raise RuntimeError("profile write failed")


def _profile_service_failing_on_the_profile_half(session: DbSession) -> ProfileService:
    return ProfileService(UserRepository(session), _FailingProfileRepository(session))


async def test_profile_edit_is_all_or_nothing():
    """PATCH /auth/me writes `users` then `physician_profiles`; both share the request's one
    transaction (app/postgresdb/dependencies.py), so a failure on the second half must roll
    back the first instead of leaving the name edited and the practice facts not."""
    user = await _create_user()

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_profile_service] = _profile_service_failing_on_the_profile_half
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
            response = client.patch(
                "/auth/me",
                json={"full_name": "Dr. Renamed", "physician_type": None, "panel_size": None},
            )
    finally:
        app.dependency_overrides.pop(get_profile_service, None)

    assert response.status_code == 500
    async with session_scope() as session:
        stored = await UserRepository(session).get_by_id(user.id)
    assert stored is not None
    assert stored.full_name == "Dr. Doe"
