"""Exercises the real auth flow end to end (login/logout/me, guard enforcement) —
everything else in the suite runs against the default_authenticated_user override in
conftest.py, so this is the one file that actually needs the real get_current_user
dependency."""

import uuid

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.auth.security import PasswordHasher
from app.postgresdb import PhysicianType, RemunerationType, UserRepository, UserRole, init_db
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


async def test_login_success_logs_an_info_record(caplog):
    _drop_auth_override()
    user = await _create_user()

    with caplog.at_level("INFO", logger="app.auth.service"):
        with TestClient(app) as client:
            client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    [record] = [r for r in caplog.records if r.name == "app.auth.service"]
    assert record.levelname == "INFO"
    assert record.email == user.email


async def test_login_without_remember_me_uses_default_expiry():
    from app.config import settings

    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    set_cookie_headers = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"]
    cookie = next(c for c in set_cookie_headers if c.startswith("nomiamd_session="))
    assert f"Max-Age={settings.jwt_expiry_seconds}" in cookie


async def test_login_with_remember_me_uses_longer_expiry():
    from app.config import settings

    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post(
            "/auth/login", json={"email": user.email, "password": PASSWORD, "remember_me": True}
        )

    set_cookie_headers = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"]
    cookie = next(c for c in set_cookie_headers if c.startswith("nomiamd_session="))
    assert f"Max-Age={settings.jwt_remember_me_expiry_seconds}" in cookie


async def test_login_wrong_password_returns_401():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": user.email, "password": "not the password"})

    assert response.status_code == 401
    assert "nomiamd_session" not in response.cookies


async def test_login_wrong_password_logs_a_warning_with_reason(caplog):
    _drop_auth_override()
    user = await _create_user()

    with caplog.at_level("WARNING", logger="app.auth.service"):
        with TestClient(app) as client:
            client.post("/auth/login", json={"email": user.email, "password": "not the password"})

    [record] = [r for r in caplog.records if r.name == "app.auth.service"]
    assert record.levelname == "WARNING"
    assert record.email == user.email
    assert record.reason == "bad_password"


async def test_login_unknown_email_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.post(
            "/auth/login", json={"email": "nobody@example.test", "password": PASSWORD}
        )

    assert response.status_code == 401


async def test_login_unknown_email_logs_a_warning_with_reason(caplog):
    _drop_auth_override()

    with caplog.at_level("WARNING", logger="app.auth.service"):
        with TestClient(app) as client:
            client.post(
                "/auth/login", json={"email": "nobody@example.test", "password": PASSWORD}
            )

    [record] = [r for r in caplog.records if r.name == "app.auth.service"]
    assert record.levelname == "WARNING"
    assert record.reason == "unknown_email"


async def test_protected_route_without_cookie_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.get("/sample-patients")

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


async def test_deactivated_user_login_logs_a_warning_with_reason(caplog):
    _drop_auth_override()
    user = await _create_user(is_active=False)

    with caplog.at_level("WARNING", logger="app.auth.service"):
        with TestClient(app) as client:
            client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    [record] = [r for r in caplog.records if r.name == "app.auth.service"]
    assert record.levelname == "WARNING"
    assert record.reason == "deactivated"


async def test_update_profile_success():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={
                "full_name": "Dr. Jane Doe",
                "physician_type": PhysicianType.MED_FAM.value,
                "number_of_patients": 500,
                "remuneration_type": RemunerationType.MIXTE.value,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Dr. Jane Doe"
    assert body["physician_type"] == PhysicianType.MED_FAM.value
    assert body["number_of_patients"] == 500
    assert body["remuneration_type"] == RemunerationType.MIXTE.value


async def test_update_profile_negative_patient_count_returns_422():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={"full_name": "Dr. Doe", "physician_type": None, "number_of_patients": -1},
        )

    assert response.status_code == 422


async def test_update_profile_invalid_physician_type_returns_422():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={"full_name": "Dr. Doe", "physician_type": "Not a real type", "number_of_patients": None},
        )

    assert response.status_code == 422


async def test_update_profile_invalid_remuneration_type_returns_422():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        response = client.patch(
            "/auth/me",
            json={
                "full_name": "Dr. Doe",
                "physician_type": None,
                "number_of_patients": None,
                "remuneration_type": "Not a real type",
            },
        )

    assert response.status_code == 422


async def test_update_profile_without_cookie_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.patch(
            "/auth/me",
            json={"full_name": "Dr. Doe", "physician_type": None, "number_of_patients": None},
        )

    assert response.status_code == 401


async def test_change_password_success_allows_login_with_new_password():
    _drop_auth_override()
    user = await _create_user()
    new_password = "a new correct horse battery staple"

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        change_response = client.post(
            "/auth/me/password",
            json={"current_password": PASSWORD, "new_password": new_password},
        )
        relogin_response = client.post(
            "/auth/login", json={"email": user.email, "password": new_password}
        )

    assert change_response.status_code == 204
    assert relogin_response.status_code == 200


async def test_change_password_wrong_current_password_returns_400_and_leaves_password_unchanged():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        change_response = client.post(
            "/auth/me/password",
            json={"current_password": "not the current password", "new_password": "irrelevant new pw"},
        )
        relogin_response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert change_response.status_code == 400
    assert relogin_response.status_code == 200


async def test_change_password_without_cookie_returns_401():
    _drop_auth_override()

    with TestClient(app) as client:
        response = client.post(
            "/auth/me/password",
            json={"current_password": PASSWORD, "new_password": "irrelevant new pw"},
        )

    assert response.status_code == 401
