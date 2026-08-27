"""Covers the property the users/physician_profiles split exists for: a claim or invoice
from the past must read the practice facts that were in effect then, not whatever the
physician's profile says today."""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.auth.security import PasswordHasher
from app.main import app
from app.postgresdb import (
    PhysicianProfileRepository,
    PhysicianType,
    RemunerationType,
    UserRepository,
    UserRole,
    init_db,
)

PASSWORD = "correct horse battery staple"


async def _create_user():
    await init_db()
    return await UserRepository().create(
        email=f"doc-{uuid.uuid4().hex[:8]}@example.test",
        hashed_password=PasswordHasher().hash(PASSWORD),
        full_name="Dr. Doe",
        role=UserRole.PHYSICIAN,
    )


async def test_no_profile_yet_reads_as_none():
    user = await _create_user()

    assert await PhysicianProfileRepository().get_current(user.id) is None


async def test_past_date_reads_the_version_in_effect_then():
    user = await _create_user()
    profiles = PhysicianProfileRepository()
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


async def test_date_before_the_first_version_reads_as_none():
    user = await _create_user()
    profiles = PhysicianProfileRepository()
    await profiles.upsert_current(
        user.id,
        physician_type=PhysicianType.MED_FAM.value,
        number_of_patients=500,
        remuneration_type=None,
        effective_from=date.today() - timedelta(days=10),
    )

    assert await profiles.get_effective_on(user.id, date.today() - timedelta(days=30)) is None


async def test_same_day_edits_overwrite_instead_of_piling_up():
    user = await _create_user()
    profiles = PhysicianProfileRepository()

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
    profiles = PhysicianProfileRepository()
    yesterday = date.today() - timedelta(days=1)

    await profiles.upsert_current(
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

    yesterdays = await profiles.get_effective_on(user.id, yesterday)
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
