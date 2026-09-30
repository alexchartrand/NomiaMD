"""Covers the property the users/physician_profiles split exists for: a claim or invoice
from the past must read the practice facts that were in effect then, not whatever the
physician's profile says today."""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.auth.factory import get_profile_service
from app.auth.profile import ProfileService
from app.auth.security import PasswordHasher
from app.main import app
from app.postgresdb import (
    DbSession,
    PhysicianProfileRepository,
    PhysicianType,
    RemunerationType,
    UserRepository,
    UserRole,
    init_db,
    session_scope,
)

PASSWORD = "correct horse battery staple"


async def _create_user():
    await init_db()
    async with session_scope() as session:
        return await UserRepository(session).create(
            email=f"doc-{uuid.uuid4().hex[:8]}@example.test",
            hashed_password=PasswordHasher().hash(PASSWORD),
            full_name="Dr. Doe",
            role=UserRole.PHYSICIAN,
        )


async def test_no_profile_yet_reads_as_none():
    user = await _create_user()

    async with session_scope() as session:
        assert await PhysicianProfileRepository(session).get_current(user.id) is None


async def test_past_date_reads_the_version_in_effect_then(db_session):
    user = await _create_user()
    profiles = PhysicianProfileRepository(db_session)
    last_year = date.today() - timedelta(days=365)

    await profiles.upsert_current(
        user.id,
        physician_type=PhysicianType.MED_FAM.value,
        number_of_patients=500,
        remuneration_type=RemunerationType.A_L_ACTE.value,
        effective_from=last_year,
    )
    await profiles.upsert_current(
        user.id,
        physician_type=PhysicianType.MED_FAM.value,
        number_of_patients=1200,
        remuneration_type=RemunerationType.MIXTE.value,
    )

    back_then = await profiles.get_effective_on(user.id, last_year + timedelta(days=30))
    assert back_then is not None
    assert back_then.number_of_patients == 500
    assert back_then.remuneration_type == RemunerationType.A_L_ACTE.value

    today = await profiles.get_current(user.id)
    assert today is not None
    assert today.number_of_patients == 1200
    assert today.remuneration_type == RemunerationType.MIXTE.value


async def test_date_before_the_first_version_reads_as_none(db_session):
    user = await _create_user()
    profiles = PhysicianProfileRepository(db_session)
    await profiles.upsert_current(
        user.id,
        physician_type=PhysicianType.MED_FAM.value,
        number_of_patients=500,
        remuneration_type=None,
        effective_from=date.today() - timedelta(days=10),
    )

    assert await profiles.get_effective_on(user.id, date.today() - timedelta(days=30)) is None


async def test_same_day_edits_overwrite_instead_of_piling_up(db_session):
    user = await _create_user()
    profiles = PhysicianProfileRepository(db_session)

    first = await profiles.upsert_current(
        user.id, physician_type=None, number_of_patients=100, remuneration_type=None
    )
    second = await profiles.upsert_current(
        user.id, physician_type=None, number_of_patients=200, remuneration_type=None
    )

    assert first.id == second.id
    current = await profiles.get_current(user.id)
    assert current is not None
    assert current.number_of_patients == 200


async def test_profile_edit_does_not_rewrite_an_earlier_version():
    """The regression the split prevents: before it, this edit mutated the single row
    every past claim's eligibility would be judged against."""
    user = await _create_user()
    yesterday = date.today() - timedelta(days=1)

    async with session_scope() as session:
        await PhysicianProfileRepository(session).upsert_current(
            user.id,
            physician_type=None,
            number_of_patients=None,
            remuneration_type=RemunerationType.A_L_ACTE.value,
            effective_from=yesterday,
        )

    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={
                "full_name": "Dr. Doe",
                "physician_type": None,
                "number_of_patients": None,
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
    assert body["number_of_patients"] is None
    assert body["remuneration_type"] is None


class _FailingProfileRepository(PhysicianProfileRepository):
    async def upsert_current(self, *args, **kwargs):
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
                json={"full_name": "Dr. Renamed", "physician_type": None, "number_of_patients": None},
            )
    finally:
        app.dependency_overrides.pop(get_profile_service, None)

    assert response.status_code == 500
    async with session_scope() as session:
        stored = await UserRepository(session).get_by_id(user.id)
    assert stored is not None
    assert stored.full_name == "Dr. Doe"
