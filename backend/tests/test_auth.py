"""Exercises the real auth flow end to end (login/logout/me, guard enforcement) —
everything else in the suite runs against the default_authenticated_user override in
conftest.py, so this is the one file that actually needs the real get_current_user
dependency."""

import uuid

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.auth.security import PasswordHasher
from app.postgresdb import UserRepository, UserRole, init_db
from app.main import app

PASSWORD = "correct horse battery staple"


async def _create_user(**overrides):
    await init_db()  # this test file may run before anything else has created the tables
    defaults = {
        "email": f"doc-{uuid.uuid4().hex[:8]}@example.test",
        "hashed_password": PasswordHasher().hash(PASSWORD),
        "full_name": "Dr. Doe",
        "role": UserRole.PHYSICIAN,
    }
    return await UserRepository().create(**{**defaults, **overrides})


def _drop_auth_override():
    app.dependency_overrides.pop(get_current_user, None)


async def test_login_success_sets_cookie_and_returns_user():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert "nomiamd_session" in response.cookies


async def test_login_wrong_password_returns_401():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": user.email, "password": "not the password"})

    assert response.status_code == 401
    assert "nomiamd_session" not in response.cookies


async def test_login_unknown_email_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.post(
            "/auth/login", json={"email": "nobody@example.test", "password": PASSWORD}
        )

    assert response.status_code == 401


async def test_protected_route_without_cookie_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.get("/patients")

    assert response.status_code == 401


async def test_me_reflects_logged_in_user():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == user.email


async def test_logout_clears_session():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        logout_response = client.post("/auth/logout")
        me_response = client.get("/auth/me")

    assert logout_response.status_code == 204
    assert me_response.status_code == 401


async def test_deactivated_user_is_rejected_even_with_a_valid_cookie():
    _drop_auth_override()
    user = await _create_user(is_active=False)

    with TestClient(app) as client:
        login_response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        assert login_response.status_code == 401
